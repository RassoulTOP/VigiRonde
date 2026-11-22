import * as Location from 'expo-location';

import type { GpsFix, LatLon } from './types';

/** Distance en mètres (formule de haversine) — sert au retour immédiat à l'agent, le serveur fait foi. */
export function distanceM(a: LatLon, b: LatLon): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Le point est-il dans le périmètre du site (avec la même tolérance de 25 m que le serveur) ? */
export function insidePerimeter(p: LatLon, polygon: { coordinates: number[][][] } | null | undefined): boolean | null {
  const ring = polygon?.coordinates?.[0];
  if (!ring?.length) return null;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > p.lat !== yj > p.lat && p.lon < ((xj - xi) * (p.lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  if (inside) return true;
  // Tolérance : à moins de 25 m d'un côté du périmètre (approximation locale suffisante à cette échelle)
  const kx = 111320 * Math.cos((p.lat * Math.PI) / 180);
  const ky = 110540;
  for (let i = 0; i < ring.length - 1; i++) {
    const ax = (ring[i][0] - p.lon) * kx, ay = (ring[i][1] - p.lat) * ky;
    const bx = (ring[i + 1][0] - p.lon) * kx, by = (ring[i + 1][1] - p.lat) * ky;
    const dx = bx - ax, dy = by - ay;
    const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy || 1)));
    if (Math.hypot(ax + t * dx, ay + t * dy) <= 25) return true;
  }
  return false;
}

export async function ensureLocationPermission(): Promise<boolean> {
  const current = await Location.getForegroundPermissionsAsync();
  if (current.granted) return true;
  const asked = await Location.requestForegroundPermissionsAsync();
  return asked.granted;
}

/** Position actuelle, ou null si le GPS ne répond pas à temps (l'action est quand même enregistrée). */
export async function currentFix(timeoutMs = 8000): Promise<GpsFix | null> {
  if (!(await ensureLocationPermission())) return null;
  const fresh = Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }).then(toFix).catch(() => null);
  const timeout = new Promise<null>((r) => setTimeout(() => r(null), timeoutMs));
  const fix = await Promise.race([fresh, timeout]);
  if (fix) return fix;
  const last = await Location.getLastKnownPositionAsync({ maxAge: 120000 }).catch(() => null);
  return last ? toFix(last) : null;
}

export function toFix(l: Location.LocationObject): GpsFix {
  return { lat: l.coords.latitude, lon: l.coords.longitude, accuracy_m: l.coords.accuracy ?? null };
}

export function formatDistance(m: number | null | undefined): string {
  if (m == null) return '—';
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}
