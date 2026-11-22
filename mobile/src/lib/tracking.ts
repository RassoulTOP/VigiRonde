/**
 * Suivi GPS pendant le service uniquement (RGPD) : un point toutes les 15 s ou tous les 10 m,
 * rattaché à la ronde en cours. Les points sont stockés sur le téléphone puis envoyés par lots.
 *
 * Note : dans Expo Go, iOS ne permet le suivi que lorsque l'appli est ouverte. Le suivi en arrière-plan
 * (écran verrouillé) sera activé dans la version installée de l'appli (development build).
 */
import * as Location from 'expo-location';
import { randomUUID } from 'expo-crypto';

import { addPositions, flush, type PositionPoint } from './outbox';
import { ensureLocationPermission } from './geo';

let sub: Location.LocationSubscription | null = null;
let ctx: { shiftId: string; roundId: string | null } | null = null;
let buffer: PositionPoint[] = [];
let lastSaved = 0;
let lastUpload = 0;
const listeners = new Set<(fix: Location.LocationObject) => void>();

export function onFix(l: (fix: Location.LocationObject) => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function setTrackingRound(roundId: string | null) {
  if (ctx) ctx.roundId = roundId;
}

export function isTracking() {
  return sub !== null;
}

export async function startTracking(shiftId: string, roundId: string | null = null): Promise<boolean> {
  ctx = { shiftId, roundId };
  if (sub) return true;
  if (!(await ensureLocationPermission())) return false;
  sub = await Location.watchPositionAsync(
    { accuracy: Location.Accuracy.High, distanceInterval: 10, timeInterval: 15000 },
    (fix) => {
      listeners.forEach((l) => l(fix));
      if (!ctx || fix.timestamp - lastSaved < 10000) return;
      lastSaved = fix.timestamp;
      buffer.push({
        client_id: randomUUID(),
        shift_id: ctx.shiftId,
        round_id: ctx.roundId,
        lat: fix.coords.latitude,
        lon: fix.coords.longitude,
        accuracy_m: fix.coords.accuracy ?? null,
        recorded_at: new Date(fix.timestamp).toISOString(),
      });
      // On écrit sur le téléphone par paquets de 4 points, et on tente l'envoi toutes les minutes
      if (buffer.length >= 4) void saveBuffer();
      if (Date.now() - lastUpload > 60000) {
        lastUpload = Date.now();
        void saveBuffer().then(flush);
      }
    },
  );
  return true;
}

async function saveBuffer() {
  if (!buffer.length) return;
  const points = buffer;
  buffer = [];
  await addPositions(points);
}

export async function stopTracking() {
  sub?.remove();
  sub = null;
  await saveBuffer();
  ctx = null;
}
