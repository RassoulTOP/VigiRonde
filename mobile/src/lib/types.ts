export type Role = 'admin' | 'superviseur' | 'agent';
export type ShiftStatus = 'planifiee' | 'en_cours' | 'terminee' | 'manquee';
export type RoundStatus = 'en_cours' | 'terminee' | 'interrompue';
export type ScanMethod = 'qr' | 'nfc' | 'manuel';

export type LatLon = { lat: number; lon: number };
export type GpsFix = LatLon & { accuracy_m?: number | null };

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  qualifications: string[];
};

export type Checkpoint = {
  id: string;
  name: string;
  code: string;
  order_index: number;
  instructions: string | null;
  location: LatLon | null;
};

export type Site = {
  id: string;
  name: string;
  client_name: string | null;
  address: string | null;
  site_type: string | null;
  location: LatLon | null;
  perimeter: { type: 'Polygon'; coordinates: number[][][] } | null;
  checkpoints: Checkpoint[];
};

export type RoundTemplate = {
  id: string;
  site_id: string;
  name: string;
  checkpoint_ids: string[];
  expected_duration_min: number;
  rounds_per_shift: number;
};

export type Shift = {
  id: string;
  site_id: string;
  site_name: string | null;
  planned_start: string;
  planned_end: string;
  actual_start: string | null;
  actual_end: string | null;
  start_inside_perimeter: boolean | null;
  status: ShiftStatus;
};

export type Scan = {
  id: string;
  checkpoint_id: string;
  checkpoint_name?: string | null;
  scanned_at: string;
  distance_m: number | null;
  method: ScanMethod;
  is_valid: boolean;
};

export type RoundOut = {
  id: string;
  shift_id: string;
  template_id: string;
  started_at: string;
  ended_at: string | null;
  status: RoundStatus;
  comment?: string | null;
  scans: Scan[];
};

/** Ronde en cours, tenue localement (fonctionne sans réseau). */
export type ActiveRound = {
  id: string;
  shiftId: string;
  templateId: string;
  startedAt: string;
  scans: Scan[];
};

export type CheckpointReport = {
  checkpoint_id: string;
  name: string;
  order_index: number;
  location: LatLon | null;
  scanned: boolean;
  scanned_at: string | null;
  distance_m: number | null;
  is_valid: boolean | null;
  minutes_since_start: number | null;
};

export type RoundReport = {
  round: RoundOut;
  site: { id: string; name: string; location?: LatLon | null; perimeter?: Site['perimeter'] };
  agent: { id: string; full_name: string };
  template: { id: string; name: string };
  duration_min: number | null;
  expected_duration_min: number;
  completion_pct: number;
  checkpoints: CheckpointReport[];
  missed_checkpoints: string[];
  out_of_order: boolean;
  distance_walked_m: number | null;
  track: { type: 'LineString'; coordinates: number[][] } | null;
  flags: string[];
};

export const INCIDENT_CATEGORIES = {
  intrusion: 'Intrusion',
  vol: 'Vol',
  degradation: 'Dégradation',
  incendie: 'Incendie / fumée',
  alarme_technique: 'Alarme technique',
  porte_ouverte: 'Porte / issue ouverte',
  personne_suspecte: 'Personne suspecte',
  malaise: 'Malaise / blessé',
  autre: 'Autre',
} as const;
export type IncidentCategory = keyof typeof INCIDENT_CATEGORIES;

export type Incident = {
  id: string;
  site_name: string | null;
  occurred_at: string;
  category: IncidentCategory;
  severity: number;
  title: string;
  status: 'ouvert' | 'en_traitement' | 'clos';
  attachments: { id: string }[];
};
