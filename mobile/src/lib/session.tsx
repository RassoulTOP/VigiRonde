/**
 * État de l'agent : connexion, vacation, site, parcours et ronde en cours.
 * Tout est gardé sur le téléphone : l'appli reste utilisable sans réseau, la boîte d'envoi
 * transmet les actions au serveur dès que possible.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import { randomUUID } from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppState } from 'react-native';

import { api, ApiError, configureApi, defaultApiUrl, getApiUrl } from './api';
import { currentFix, distanceM, insidePerimeter } from './geo';
import { clearOutbox, enqueue, flush, keepFile, loadOutbox, outbox, setOnline } from './outbox';
import { setTrackingRound, startTracking, stopTracking } from './tracking';
import type {
  ActiveRound,
  Checkpoint,
  GpsFix,
  IncidentCategory,
  RoundOut,
  RoundTemplate,
  Scan,
  ScanMethod,
  Shift,
  Site,
  User,
} from './types';

const TOKEN_KEY = 'vigironde.token';
const STATE_KEY = 'vigironde.session.v1';
/** Même règle que le serveur : 60 m + précision GPS (plafonnée à 50 m). */
const MAX_SCAN_DISTANCE_M = 60;

type Persisted = {
  apiUrl: string;
  user: User | null;
  shift: Shift | null;
  site: Site | null;
  templates: RoundTemplate[];
  activeRound: ActiveRound | null;
  lastRoundId: string | null;
};

const EMPTY: Persisted = {
  apiUrl: defaultApiUrl(),
  user: null,
  shift: null,
  site: null,
  templates: [],
  activeRound: null,
  lastRoundId: null,
};

export type ScanResult =
  | { ok: false; message: string }
  | { ok: true; checkpoint: Checkpoint; distance: number | null; valid: boolean; alreadyScanned: boolean; fix: GpsFix | null };

export type NewIncident = {
  category: IncidentCategory;
  severity: number;
  title: string;
  description: string;
  photos: { uri: string; mimeType?: string | null }[];
};

type Session = Persisted & {
  ready: boolean;
  token: string | null;
  refreshing: boolean;
  login: (email: string, password: string, apiUrl: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  startShift: () => Promise<{ inside: boolean | null; fix: GpsFix | null }>;
  endShift: () => Promise<void>;
  startRound: (templateId: string) => Promise<void>;
  scan: (code: string, method: ScanMethod) => Promise<ScanResult>;
  endRound: (opts: { interrupted: boolean; comment?: string }) => Promise<string>;
  reportIncident: (inc: NewIncident) => Promise<void>;
};

const Ctx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error('useSession hors de SessionProvider');
  return s;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [data, setData] = useState<Persisted>(EMPTY);
  const [refreshing, setRefreshing] = useState(false);
  const dataRef = useRef(data); // copie synchrone de `data`, tenue à jour par update()

  const update = useCallback((patch: Partial<Persisted>) => {
    const next = { ...dataRef.current, ...patch };
    dataRef.current = next;
    setData(next);
    void AsyncStorage.setItem(STATE_KEY, JSON.stringify(next));
  }, []);

  const logout = useCallback(async () => {
    await stopTracking();
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    configureApi({ token: null });
    setToken(null);
    update({ ...EMPTY, apiUrl: dataRef.current.apiUrl });
  }, [update]);

  // Démarrage : restaure la session et la boîte d'envoi
  useEffect(() => {
    (async () => {
      await loadOutbox();
      const raw = await AsyncStorage.getItem(STATE_KEY);
      const saved: Persisted = raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY;
      const t = await SecureStore.getItemAsync(TOKEN_KEY);
      configureApi({ baseUrl: saved.apiUrl, token: t, onUnauthorized: () => void logout() });
      dataRef.current = saved;
      setData(saved);
      setToken(t);
      if (t && saved.shift?.status === 'en_cours') {
        await startTracking(saved.shift.id, saved.activeRound?.id ?? null);
      }
      setReady(true);
    })();
  }, [logout]);

  // Réseau retrouvé / appli revenue au premier plan → synchronisation
  useEffect(() => {
    const unNet = NetInfo.addEventListener((s) => setOnline(!!s.isConnected && s.isInternetReachable !== false));
    const unApp = AppState.addEventListener('change', (s) => s === 'active' && void flush());
    const timer = setInterval(() => void flush(), 30000);
    return () => {
      unNet();
      unApp.remove();
      clearInterval(timer);
    };
  }, []);

  /** Recharge vacation, site et parcours depuis le serveur (sans effet si hors-ligne). */
  const sync = useCallback(async () => {
    if (!token) return;
    try {
      await flush();
      // Tant que des actions attendent d'être envoyées, la version du téléphone fait foi
      if (outbox.get().ops.length) return;
      let shift = await api<Shift | null>('/shifts/current');
      if (!shift) {
        const now = Date.now();
        const upcoming = await api<Shift[]>('/shifts', {
          query: {
            status: 'planifiee',
            start: new Date(now - 6 * 3600e3).toISOString(),
            end: new Date(now + 36 * 3600e3).toISOString(),
            limit: 20,
          },
        });
        shift = upcoming.sort((a, b) => a.planned_start.localeCompare(b.planned_start))[0] ?? null;
      }
      let { site, templates, activeRound } = dataRef.current;
      if (shift) {
        if (site?.id !== shift.site_id || !templates.length) {
          [site, templates] = await Promise.all([
            api<Site>(`/sites/${shift.site_id}`),
            api<RoundTemplate[]>('/round-templates', { query: { site_id: shift.site_id } }),
          ]);
        }
        if (shift.status === 'en_cours') {
          const rounds = await api<RoundOut[]>('/rounds', { query: { shift_id: shift.id, limit: 5 } });
          const open = rounds.find((r) => r.status === 'en_cours');
          activeRound = open
            ? { id: open.id, shiftId: open.shift_id, templateId: open.template_id, startedAt: open.started_at, scans: open.scans }
            : null;
          await startTracking(shift.id, activeRound?.id ?? null);
          setTrackingRound(activeRound?.id ?? null);
        } else {
          activeRound = null;
          await stopTracking();
        }
      } else {
        site = null;
        templates = [];
        activeRound = null;
        await stopTracking();
      }
      update({ shift, site, templates, activeRound });
    } catch (e) {
      if (!(e instanceof ApiError)) return; // hors-ligne : on garde l'état local
      throw e;
    }
  }, [token, update]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await sync();
    } finally {
      setRefreshing(false);
    }
  }, [sync]);

  useEffect(() => {
    if (ready && token) void sync().catch(() => undefined);
  }, [ready, token, sync]);

  const login = useCallback(
    async (email: string, password: string, apiUrl: string) => {
      configureApi({ baseUrl: apiUrl });
      const form = new URLSearchParams({ username: email.trim(), password });
      const res = await api<{ access_token: string }>('/auth/login', { form });
      configureApi({ token: res.access_token });
      const user = await api<User>('/auth/me');
      // Changement d'agent sur le même téléphone : on repart d'une boîte d'envoi vide
      if (dataRef.current.user && dataRef.current.user.id !== user.id) await clearOutbox();
      await SecureStore.setItemAsync(TOKEN_KEY, res.access_token);
      update({ ...EMPTY, apiUrl: getApiUrl(), user });
      setToken(res.access_token);
    },
    [update],
  );

  const startShift = useCallback(async () => {
    const { shift, site } = dataRef.current;
    if (!shift || shift.status !== 'planifiee') throw new Error('Aucune vacation à commencer');
    const fix = await currentFix();
    const at = new Date().toISOString();
    const inside = fix ? insidePerimeter(fix, site?.perimeter) : null;
    await enqueue({
      label: 'Prise de service',
      method: 'POST',
      path: `/shifts/${shift.id}/start`,
      body: { position: fix, at },
      doneStatuses: [409],
    });
    update({ shift: { ...shift, status: 'en_cours', actual_start: at, start_inside_perimeter: inside } });
    await startTracking(shift.id);
    return { inside, fix };
  }, [update]);

  const endShift = useCallback(async () => {
    const { shift, activeRound } = dataRef.current;
    if (!shift || shift.status !== 'en_cours') throw new Error('Aucune vacation en cours');
    if (activeRound) throw new Error("Terminez d'abord la ronde en cours");
    const fix = await currentFix();
    await stopTracking();
    await enqueue({
      label: 'Fin de service',
      method: 'POST',
      path: `/shifts/${shift.id}/end`,
      body: { position: fix, at: new Date().toISOString() },
      doneStatuses: [409],
    });
    update({ shift: { ...shift, status: 'terminee', actual_end: new Date().toISOString() } });
  }, [update]);

  const startRound = useCallback(
    async (templateId: string) => {
      const { shift, activeRound } = dataRef.current;
      if (!shift || shift.status !== 'en_cours') throw new Error("Commencez d'abord votre vacation");
      if (activeRound) throw new Error('Une ronde est déjà en cours');
      const id = randomUUID();
      const at = new Date().toISOString();
      const fix = await currentFix(5000);
      await enqueue({
        label: 'Début de ronde',
        method: 'POST',
        path: '/rounds',
        body: { id, shift_id: shift.id, template_id: templateId, position: fix, at },
      });
      setTrackingRound(id);
      update({ activeRound: { id, shiftId: shift.id, templateId, startedAt: at, scans: [] } });
    },
    [update],
  );

  const scan = useCallback(
    async (rawCode: string, method: ScanMethod): Promise<ScanResult> => {
      const { site, templates, activeRound } = dataRef.current;
      if (!activeRound) return { ok: false, message: 'Aucune ronde en cours' };
      const code = rawCode.trim();
      const cp = site?.checkpoints.find((c) => c.code.toUpperCase() === code.toUpperCase());
      const tpl = templates.find((t) => t.id === activeRound.templateId);
      if (!cp) return { ok: false, message: `Code « ${code} » inconnu sur ce site` };
      if (tpl && !tpl.checkpoint_ids.includes(cp.id)) {
        return { ok: false, message: `« ${cp.name} » ne fait pas partie de ce parcours` };
      }
      const fix = await currentFix(5000);
      const distance = fix && cp.location ? distanceM(fix, cp.location) : null;
      const valid = distance == null || distance <= MAX_SCAN_DISTANCE_M + Math.min(fix?.accuracy_m ?? 0, 50);
      const alreadyScanned = activeRound.scans.some((s) => s.checkpoint_id === cp.id);
      const s: Scan = {
        id: randomUUID(),
        checkpoint_id: cp.id,
        checkpoint_name: cp.name,
        scanned_at: new Date().toISOString(),
        distance_m: distance,
        method,
        is_valid: valid,
      };
      await enqueue({
        label: `Scan « ${cp.name} »`,
        method: 'POST',
        path: `/rounds/${activeRound.id}/scan`,
        body: { id: s.id, code: cp.code, method, position: fix, at: s.scanned_at },
      });
      update({ activeRound: { ...activeRound, scans: [...activeRound.scans, s] } });
      return { ok: true, checkpoint: cp, distance, valid, alreadyScanned, fix };
    },
    [update],
  );

  const endRound = useCallback(
    async ({ interrupted, comment }: { interrupted: boolean; comment?: string }) => {
      const { activeRound } = dataRef.current;
      if (!activeRound) throw new Error('Aucune ronde en cours');
      const fix = await currentFix(5000);
      await enqueue({
        label: interrupted ? 'Ronde interrompue' : 'Fin de ronde',
        method: 'POST',
        path: `/rounds/${activeRound.id}/end`,
        body: { position: fix, at: new Date().toISOString(), comment: comment || null, interrupted },
        doneStatuses: [409],
      });
      setTrackingRound(null);
      update({ activeRound: null, lastRoundId: activeRound.id });
      return activeRound.id;
    },
    [update],
  );

  const reportIncident = useCallback(async (inc: NewIncident) => {
    const { shift, activeRound } = dataRef.current;
    if (!shift) throw new Error('Aucune vacation : impossible de rattacher l’incident à un site');
    const id = randomUUID();
    const fix = await currentFix(5000);
    await enqueue({
      label: `Incident « ${inc.title} »`,
      method: 'POST',
      path: '/incidents',
      body: {
        id,
        client_id: id,
        site_id: shift.site_id,
        shift_id: shift.status === 'en_cours' ? shift.id : null,
        round_id: activeRound?.id ?? null,
        occurred_at: new Date().toISOString(),
        position: fix,
        category: inc.category,
        severity: inc.severity,
        title: inc.title,
        description_raw: inc.description,
      },
    });
    for (const [i, photo] of inc.photos.entries()) {
      const attId = randomUUID();
      const type = photo.mimeType ?? 'image/jpeg';
      const ext = type === 'image/png' ? '.png' : type === 'image/heic' ? '.heic' : '.jpg';
      const uri = keepFile(photo.uri, attId + ext);
      await enqueue({
        label: `Photo ${i + 1} de l’incident`,
        method: 'POST',
        path: `/incidents/${id}/attachments`,
        query: { attachment_id: attId },
        file: { uri, name: `photo-${i + 1}${ext}`, type },
      });
    }
  }, []);

  const value = useMemo<Session>(
    () => ({
      ...data,
      ready,
      token,
      refreshing,
      login,
      logout,
      refresh,
      startShift,
      endShift,
      startRound,
      scan,
      endRound,
      reportIncident,
    }),
    [data, ready, token, refreshing, login, logout, refresh, startShift, endShift, startRound, scan, endRound, reportIncident],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
