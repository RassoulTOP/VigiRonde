import Constants from 'expo-constants';

/** Erreur renvoyée par le serveur (4xx / 5xx). */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Serveur injoignable (pas de réseau, délai dépassé…). */
export class NetworkError extends Error {}

let baseUrl = defaultApiUrl();
let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

/** En développement, l'API tourne sur le même Mac que Metro (port 8000). */
export function defaultApiUrl(): string {
  const host = Constants.expoConfig?.hostUri?.split(':')[0];
  return host ? `http://${host}:8000` : 'http://localhost:8000';
}

export function configureApi(opts: { baseUrl?: string; token?: string | null; onUnauthorized?: () => void }) {
  if (opts.baseUrl !== undefined) baseUrl = opts.baseUrl.replace(/\/+$/, '');
  if (opts.token !== undefined) token = opts.token;
  if (opts.onUnauthorized) onUnauthorized = opts.onUnauthorized;
}

export const getApiUrl = () => baseUrl;
export const getToken = () => token;

type Options = {
  method?: 'GET' | 'POST' | 'PATCH';
  body?: unknown;
  form?: FormData | URLSearchParams;
  query?: Record<string, string | number | undefined>;
  timeoutMs?: number;
};

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const { method = opts.body || opts.form ? 'POST' : 'GET', timeoutMs = 15000 } = opts;
  const qs = opts.query
    ? '?' +
      Object.entries(opts.query)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
        .join('&')
    : '';
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(opts.body);
  } else if (opts.form) {
    payload = opts.form as BodyInit;
    if (opts.form instanceof URLSearchParams) {
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
      payload = opts.form.toString();
    }
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(baseUrl + path + qs, { method, headers, body: payload, signal: ctrl.signal });
  } catch {
    throw new NetworkError('Serveur injoignable');
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized?.();
    throw new ApiError(res.status, errorMessage(data) ?? `Erreur ${res.status}`);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function errorMessage(data: unknown): string | null {
  if (data && typeof data === 'object' && 'detail' in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((e) => e?.msg ?? String(e)).join(' · ');
  }
  return typeof data === 'string' ? data : null;
}
