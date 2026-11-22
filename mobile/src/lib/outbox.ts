/**
 * File d'attente hors-ligne (« boîte d'envoi »).
 *
 * Chaque action de l'agent (prise de service, scan, incident, photo…) est d'abord enregistrée sur le
 * téléphone, puis envoyée au serveur dans l'ordre dès que le réseau le permet. Les identifiants sont
 * générés par l'appli : un renvoi après coupure ne crée jamais de doublon côté serveur.
 * Les positions GPS ont leur propre tampon, envoyé par lots une fois les actions passées.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Directory, File, Paths } from 'expo-file-system';
import { randomUUID } from 'expo-crypto';

import { api, ApiError, getToken, NetworkError } from './api';

export type Op = {
  id: string;
  label: string;
  method: 'POST' | 'PATCH';
  path: string;
  body?: unknown;
  query?: Record<string, string>;
  file?: { uri: string; name: string; type: string };
  /** Codes HTTP signifiant « déjà fait » (ex. 409 sur une vacation déjà commencée). */
  doneStatuses?: number[];
  createdAt: string;
  attempts: number;
  lastError?: string;
};

export type FailedOp = Op & { failedAt: string };

export type PositionPoint = {
  client_id: string;
  shift_id: string;
  round_id: string | null;
  lat: number;
  lon: number;
  accuracy_m: number | null;
  recorded_at: string;
};

type State = {
  ops: Op[];
  failed: FailedOp[];
  positions: PositionPoint[];
  syncing: boolean;
  lastSyncAt: string | null;
  online: boolean;
};

const KEY = 'vigironde.outbox.v1';
const MAX_POSITIONS = 20000; // ~3 jours de points : au-delà on garde les plus récents
let state: State = { ops: [], failed: [], positions: [], syncing: false, lastSyncAt: null, online: true };
const listeners = new Set<() => void>();
let loaded = false;

function emit(next: Partial<State>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

async function persist() {
  const { ops, failed, positions, lastSyncAt } = state;
  await AsyncStorage.setItem(KEY, JSON.stringify({ ops, failed, positions, lastSyncAt }));
}

export async function loadOutbox() {
  if (loaded) return;
  loaded = true;
  const raw = await AsyncStorage.getItem(KEY);
  if (raw) {
    const saved = JSON.parse(raw);
    emit({ ops: saved.ops ?? [], failed: saved.failed ?? [], positions: saved.positions ?? [], lastSyncAt: saved.lastSyncAt ?? null });
  }
}

export const outbox = {
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
  get: () => state,
};

export async function enqueue(op: Omit<Op, 'id' | 'createdAt' | 'attempts'>) {
  emit({ ops: [...state.ops, { ...op, id: randomUUID(), createdAt: new Date().toISOString(), attempts: 0 }] });
  await persist();
  void flush();
}

export async function addPositions(points: PositionPoint[]) {
  const positions = [...state.positions, ...points].slice(-MAX_POSITIONS);
  emit({ positions });
  await persist();
}

export async function dismissFailed(id: string) {
  emit({ failed: state.failed.filter((f) => f.id !== id) });
  await persist();
}

export async function clearOutbox() {
  emit({ ops: [], failed: [], positions: [], lastSyncAt: null });
  await persist();
}

export function setOnline(online: boolean) {
  if (online !== state.online) emit({ online });
  if (online) void flush();
}

/** Copie une photo dans le stockage durable de l'appli (le cache peut être vidé par iOS). */
export function keepFile(uri: string, name: string): string {
  const dir = new Directory(Paths.document, 'pieces-jointes');
  if (!dir.exists) dir.create({ intermediates: true, idempotent: true });
  const dest = new File(dir, name);
  if (!dest.exists) new File(uri).copy(dest);
  return dest.uri;
}

function deleteKeptFile(uri: string) {
  try {
    const f = new File(uri);
    if (f.uri.includes('pieces-jointes') && f.exists) f.delete();
  } catch {
    // fichier déjà supprimé : sans importance
  }
}

async function send(op: Op) {
  if (op.file) {
    const form = new FormData();
    // Format attendu par React Native pour envoyer un fichier local
    form.append('file', { uri: op.file.uri, name: op.file.name, type: op.file.type } as unknown as Blob);
    await api(op.path, { method: 'POST', form, query: op.query, timeoutMs: 60000 });
  } else {
    await api(op.path, { method: op.method, body: op.body ?? {}, query: op.query });
  }
}

let flushing: Promise<void> | null = null;

/** Envoie tout ce qui est en attente, dans l'ordre. S'arrête à la première coupure réseau. */
export function flush(): Promise<void> {
  if (!flushing) flushing = doFlush().finally(() => (flushing = null));
  return flushing;
}

async function doFlush() {
  if (!getToken()) return;
  emit({ syncing: true });
  try {
    while (state.ops.length) {
      const op = state.ops[0];
      try {
        await send(op);
      } catch (e) {
        if (e instanceof NetworkError) {
          emit({ online: false, ops: [{ ...op, attempts: op.attempts + 1, lastError: e.message }, ...state.ops.slice(1)] });
          return;
        }
        const alreadyDone = e instanceof ApiError && (op.doneStatuses ?? []).includes(e.status);
        if (e instanceof ApiError && (e.status === 401 || e.status >= 500)) {
          // session expirée ou serveur en difficulté : on réessaiera plus tard
          emit({ ops: [{ ...op, attempts: op.attempts + 1, lastError: e.message }, ...state.ops.slice(1)] });
          return;
        }
        if (!alreadyDone) {
          // Refus définitif (donnée invalide, fichier disparu…) : mis de côté pour que l'agent le voie
          const message = e instanceof Error ? e.message : String(e);
          emit({ failed: [...state.failed, { ...op, lastError: message, failedAt: new Date().toISOString() }] });
        }
      }
      if (op.file) deleteKeptFile(op.file.uri);
      emit({ online: true, ops: state.ops.slice(1) });
      await persist();
    }
    await flushPositions();
    emit({ lastSyncAt: new Date().toISOString() });
  } finally {
    emit({ syncing: false });
    await persist();
  }
}

async function flushPositions() {
  while (state.positions.length) {
    const shiftId = state.positions[0].shift_id;
    const batch = state.positions.filter((p) => p.shift_id === shiftId).slice(0, 500);
    try {
      await api('/positions/batch', {
        body: {
          shift_id: shiftId,
          positions: batch.map(({ shift_id: _s, ...p }) => p),
        },
      });
    } catch (e) {
      if (e instanceof NetworkError) {
        emit({ online: false });
        return;
      }
      if (!(e instanceof ApiError) || e.status === 401 || e.status >= 500) return;
      // 4xx : vacation inconnue ou close côté serveur → ces points ne seront jamais acceptés
    }
    const sent = new Set(batch.map((p) => p.client_id));
    emit({ positions: state.positions.filter((p) => !sent.has(p.client_id)) });
    await persist();
  }
}
