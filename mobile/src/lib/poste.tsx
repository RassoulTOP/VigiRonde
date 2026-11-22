/**
 * Fonctions de poste : rapports à modèles, main courante, consignes, clés, visiteurs, pause et PTI.
 * Même principe que la session : données gardées sur le téléphone, actions envoyées par la boîte d'envoi
 * (identifiants générés ici, donc aucun doublon), affichage mis à jour immédiatement.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { randomUUID } from 'expo-crypto';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { api, ApiError } from './api';
import { currentFix } from './geo';
import { enqueue, flush, outbox } from './outbox';
import { useSession } from './session';
import type {
  AlertKind,
  Instruction,
  JournalEntry,
  PtiAlert,
  QuickEvent,
  ReportTemplate,
  SiteKey,
  Visit,
} from './types';

const KEY = 'vigironde.poste.v1';

type Data = {
  siteId: string | null;
  reportTemplates: ReportTemplate[];
  quickEvents: QuickEvent[];
  instructions: Instruction[];
  keys: SiteKey[];
  visits: Visit[]; // visiteurs présents
  journal: JournalEntry[];
  pause: { id: string; startedAt: string } | null;
  alert: PtiAlert | null; // dernière alerte PTI de l'agent
  ptiEnabled: boolean;
  ptiDelaySec: number; // délai d'immobilité avant pré-alarme
};

const EMPTY: Data = {
  siteId: null,
  reportTemplates: [],
  quickEvents: [],
  instructions: [],
  keys: [],
  visits: [],
  journal: [],
  pause: null,
  alert: null,
  ptiEnabled: true,
  ptiDelaySec: 120,
};

export type NewVisit = {
  visitor_name: string;
  company?: string;
  reason?: string;
  host_name?: string;
  vehicle_plate?: string;
  badge_number?: string;
};

type Poste = Data & {
  syncing: boolean;
  sync: () => Promise<void>;
  loadJournal: () => Promise<void>;
  addJournal: (text: string, kind?: 'evenement' | 'note') => Promise<void>;
  ackInstruction: (id: string) => Promise<void>;
  moveKey: (key: SiteKey, action: 'sortie' | 'retour', holder: string, company?: string) => Promise<void>;
  addVisit: (v: NewVisit) => Promise<void>;
  exitVisit: (id: string) => Promise<void>;
  startPause: () => Promise<void>;
  endPause: () => Promise<void>;
  raiseAlert: (kind: AlertKind) => Promise<PtiAlert>;
  cancelAlert: () => Promise<void>;
  refreshAlert: () => Promise<void>;
  setPti: (opts: { enabled?: boolean; delaySec?: number }) => void;
  draftReport: (body: {
    template_id: string | null;
    title: string;
    description: string;
    answers: Record<string, unknown>;
    severity: number;
  }) => Promise<{ text: string; source: 'ia' | 'modele' }>;
};

const Ctx = createContext<Poste | null>(null);

export function usePoste(): Poste {
  const p = useContext(Ctx);
  if (!p) throw new Error('usePoste hors de PosteProvider');
  return p;
}

export function PosteProvider({ children }: { children: ReactNode }) {
  const { shift, site, token } = useSession();
  const [data, setData] = useState<Data>(EMPTY);
  const [syncing, setSyncing] = useState(false);
  const ref = useRef(data);

  const update = useCallback((patch: Partial<Data> | ((d: Data) => Partial<Data>)) => {
    const next = { ...ref.current, ...(typeof patch === 'function' ? patch(ref.current) : patch) };
    ref.current = next;
    setData(next);
    void AsyncStorage.setItem(KEY, JSON.stringify(next));
  }, []);

  useEffect(() => {
    void AsyncStorage.getItem(KEY).then((raw) => {
      if (!raw) return;
      const saved = { ...EMPTY, ...JSON.parse(raw) } as Data;
      ref.current = saved;
      setData(saved);
    });
  }, []);

  const shiftId = shift?.status === 'en_cours' ? shift.id : null;
  const siteId = shift && shift.status !== 'terminee' ? (site?.id ?? shift.site_id) : null;

  const loadJournal = useCallback(async () => {
    if (!shiftId) return;
    const rows = await api<JournalEntry[]>('/journal', { query: { shift_id: shiftId, limit: 150 } });
    update({ journal: rows });
  }, [shiftId, update]);

  /** Recharge les données du poste (sans indicateur : appelée aussi au changement de site). */
  const fetchPoste = useCallback(async () => {
    if (!token || !siteId) return;
    try {
      await flush();
      if (siteId !== ref.current.siteId) {
        // Nouveau site : on repart de zéro (en gardant les réglages PTI)
        update({ ...EMPTY, ptiEnabled: ref.current.ptiEnabled, ptiDelaySec: ref.current.ptiDelaySec, siteId });
      }
      const pendingOps = outbox.get().ops.length > 0;
      const [reportTemplates, quickEvents, instructions, keys, visits] = await Promise.all([
        api<ReportTemplate[]>('/report-templates', { query: { site_id: siteId } }),
        api<QuickEvent[]>('/journal/quick-events'),
        api<Instruction[]>('/instructions', { query: { site_id: siteId } }),
        api<SiteKey[]>('/keys', { query: { site_id: siteId } }),
        api<Visit[]>('/visits', { query: { site_id: siteId, present: 'true' } }),
      ]);
      // Si des actions attendent encore l'envoi, on garde la version locale (plus récente)
      update(pendingOps && ref.current.siteId === siteId
        ? { reportTemplates, quickEvents }
        : { siteId, reportTemplates, quickEvents, instructions, keys, visits });
      if (shift?.status === 'en_cours' && !pendingOps) {
        update({
          pause: shift.active_pause_id && shift.active_pause_started_at
            ? { id: shift.active_pause_id, startedAt: shift.active_pause_started_at }
            : null,
        });
      }
      if (shiftId) await loadJournal();
    } catch (e) {
      if (e instanceof ApiError) throw e; // hors-ligne : on garde le cache
    }
  }, [token, siteId, shiftId, shift, update, loadJournal]);

  const sync = useCallback(async () => {
    setSyncing(true);
    try {
      await fetchPoste();
    } finally {
      setSyncing(false);
    }
  }, [fetchPoste]);

  useEffect(() => {
    if (siteId) void fetchPoste().catch(() => undefined);
  }, [siteId, fetchPoste]);

  const pushJournalLocal = useCallback(
    (text: string, kind: JournalEntry['kind']) =>
      update((d) => ({
        journal: [
          { id: randomUUID(), occurred_at: new Date().toISOString(), kind, text, agent_name: null, pending: true },
          ...d.journal,
        ],
      })),
    [update],
  );

  const addJournal = useCallback(
    async (text: string, kind: 'evenement' | 'note' = 'evenement') => {
      if (!shiftId) throw new Error('Prenez votre service pour écrire en main courante');
      const fix = await currentFix(4000);
      const id = randomUUID();
      await enqueue({
        label: `Main courante « ${text.slice(0, 40)} »`,
        method: 'POST',
        path: '/journal',
        body: { id, shift_id: shiftId, kind, text, position: fix, at: new Date().toISOString() },
      });
      pushJournalLocal(text, kind);
    },
    [shiftId, pushJournalLocal],
  );

  const ackInstruction = useCallback(
    async (id: string) => {
      const at = new Date().toISOString();
      await enqueue({ label: 'Consigne validée', method: 'POST', path: `/instructions/${id}/ack`, body: { shift_id: shiftId, at } });
      update((d) => ({ instructions: d.instructions.map((i) => (i.id === id ? { ...i, acked_at: at } : i)) }));
    },
    [shiftId, update],
  );

  const moveKey = useCallback(
    async (key: SiteKey, action: 'sortie' | 'retour', holder: string, company?: string) => {
      const at = new Date().toISOString();
      await enqueue({
        label: `Clé « ${key.label} » ${action === 'sortie' ? 'remise' : 'rendue'}`,
        method: 'POST',
        path: `/keys/${key.id}/movements`,
        body: { id: randomUUID(), shift_id: shiftId, action, holder_name: holder, holder_company: company || null, at },
      });
      update((d) => ({
        keys: d.keys.map((k) =>
          k.id === key.id
            ? action === 'sortie'
              ? { ...k, is_out: true, holder_name: holder, holder_company: company || null, since: at }
              : { ...k, is_out: false, holder_name: null, holder_company: null, since: at }
            : k,
        ),
      }));
      pushJournalLocal(`Clé « ${key.label} » ${action === 'sortie' ? 'remise à' : 'rendue par'} ${holder}`, 'clef');
    },
    [shiftId, update, pushJournalLocal],
  );

  const addVisit = useCallback(
    async (v: NewVisit) => {
      if (!siteId) throw new Error('Aucun site');
      const id = randomUUID();
      const at = new Date().toISOString();
      const clean = Object.fromEntries(Object.entries(v).map(([k, val]) => [k, val?.trim() || null]));
      await enqueue({
        label: `Visiteur ${v.visitor_name}`,
        method: 'POST',
        path: '/visits',
        body: { id, site_id: siteId, shift_id: shiftId, at, ...clean },
      });
      const plate = v.vehicle_plate?.trim().toUpperCase().replace(/\s+/g, '-') || null;
      update((d) => ({
        visits: [
          { id, arrived_at: at, left_at: null, company: null, reason: null, host_name: null, badge_number: null, ...clean, vehicle_plate: plate, visitor_name: v.visitor_name.trim() } as Visit,
          ...d.visits,
        ],
      }));
      pushJournalLocal(`Arrivée visiteur : ${v.visitor_name}`, 'visiteur');
    },
    [siteId, shiftId, update, pushJournalLocal],
  );

  const exitVisit = useCallback(
    async (id: string) => {
      const v = ref.current.visits.find((x) => x.id === id);
      await enqueue({ label: `Départ ${v?.visitor_name ?? 'visiteur'}`, method: 'POST', path: `/visits/${id}/exit`, body: { at: new Date().toISOString() } });
      update((d) => ({ visits: d.visits.filter((x) => x.id !== id) }));
      if (v) pushJournalLocal(`Départ visiteur : ${v.visitor_name}`, 'visiteur');
    },
    [update, pushJournalLocal],
  );

  const startPause = useCallback(async () => {
    if (!shiftId) throw new Error('Aucune vacation en cours');
    const id = randomUUID();
    const at = new Date().toISOString();
    await enqueue({ label: 'Début de pause', method: 'POST', path: `/shifts/${shiftId}/pauses`, body: { id, at }, doneStatuses: [409] });
    update({ pause: { id, startedAt: at } });
    pushJournalLocal('Début de pause', 'pause');
  }, [shiftId, update, pushJournalLocal]);

  const endPause = useCallback(async () => {
    const p = ref.current.pause;
    if (!shiftId || !p) return;
    await enqueue({ label: 'Fin de pause', method: 'POST', path: `/shifts/${shiftId}/pauses/${p.id}/end`, body: { at: new Date().toISOString() } });
    update({ pause: null });
    pushJournalLocal(`Fin de pause (${Math.round((Date.now() - new Date(p.startedAt).getTime()) / 60000)} min)`, 'pause');
  }, [shiftId, update, pushJournalLocal]);

  /** Alerte PTI : envoi direct prioritaire ; sans réseau, mise en file et nouvel essai automatique. */
  const raiseAlert = useCallback(
    async (kind: AlertKind) => {
      const id = randomUUID();
      const at = new Date().toISOString();
      const fix = await currentFix(4000);
      const body = { id, kind, shift_id: shiftId, position: fix, at };
      let alert: PtiAlert = { id, kind, status: kind === 'test' ? 'close' : 'active', triggered_at: at, sent: false };
      try {
        const res = await api<PtiAlert>('/alerts', { body, timeoutMs: 8000 });
        alert = { ...alert, ...res, sent: true };
      } catch {
        await enqueue({ label: kind === 'test' ? 'Test PTI' : 'ALERTE PTI', method: 'POST', path: '/alerts', body });
      }
      if (kind !== 'test') update({ alert });
      return alert;
    },
    [shiftId, update],
  );

  const cancelAlert = useCallback(async () => {
    const a = ref.current.alert;
    if (!a) return;
    await enqueue({ label: 'Annulation alerte', method: 'POST', path: `/alerts/${a.id}/cancel`, body: { note: 'fausse alerte' } });
    update({ alert: { ...a, status: 'annulee' } });
  }, [update]);

  const refreshAlert = useCallback(async () => {
    const a = ref.current.alert;
    if (!a || a.status === 'annulee' || a.status === 'close') return;
    try {
      const res = await api<PtiAlert>(`/alerts/${a.id}`);
      update({ alert: { ...a, ...res, sent: true } });
    } catch {
      // pas encore reçue ou hors-ligne
    }
  }, [update]);

  const setPti = useCallback(
    ({ enabled, delaySec }: { enabled?: boolean; delaySec?: number }) =>
      update((d) => ({ ptiEnabled: enabled ?? d.ptiEnabled, ptiDelaySec: delaySec ?? d.ptiDelaySec })),
    [update],
  );

  const draftReport = useCallback<Poste['draftReport']>(
    async (body) => {
      if (!siteId) throw new Error('Aucun site');
      return api('/reports/draft', { body: { ...body, site_id: siteId, occurred_at: new Date().toISOString() }, timeoutMs: 60000 });
    },
    [siteId],
  );

  const value = useMemo<Poste>(
    () => ({
      ...data,
      syncing,
      sync,
      loadJournal,
      addJournal,
      ackInstruction,
      moveKey,
      addVisit,
      exitVisit,
      startPause,
      endPause,
      raiseAlert,
      cancelAlert,
      refreshAlert,
      setPti,
      draftReport,
    }),
    [data, syncing, sync, loadJournal, addJournal, ackInstruction, moveKey, addVisit, exitVisit, startPause, endPause, raiseAlert, cancelAlert, refreshAlert, setPti, draftReport],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
