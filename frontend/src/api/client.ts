import type { components } from './generated';
export type Schema = components['schemas'];
export type Replay = Schema['ReplaySnapshot'];
export type ReplayEvent = Schema['ReplayEvent'];
export type Prediction = Schema['ReplayPrediction'];
export type Telemetry = Schema['ReplayTelemetry'];
export type EpisodeEvent = Schema['EpisodeTransition'];
export type Well = Schema['WellInfo'];
export type Model = Schema['ModelInfo'];

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string) { super(message); }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const timeout = AbortSignal.timeout(15000);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  let response: Response;
  try { response = await fetch(`/api${path}`, { ...init, signal, headers: { 'Accept': 'application/json', ...init.headers } }); }
  catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError(0, 'CONNECTION_UNAVAILABLE', 'Backend connection unavailable. Check the local API and retry.');
  }
  let value: unknown;
  try { value = await response.json(); } catch { throw new ApiError(response.status, 'INVALID_RESPONSE', 'Backend returned an unreadable response.'); }
  if (!response.ok) {
    const packet = value as { error?: { code?: string; message?: string; request_id?: string } };
    throw new ApiError(response.status, packet.error?.code ?? 'REQUEST_FAILED', packet.error?.message ?? `Request failed (${response.status}).`, packet.error?.request_id);
  }
  return value as T;
}
const query = (values: Record<string, string | number | undefined>) => {
  const parameters = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined) parameters.set(key, String(value)); });
  return `?${parameters}`;
};
export function mutation<T>(path: string, body: unknown, key: string = crypto.randomUUID()) {
  // The same closure retains its key/body for a deliberate retry after transport ambiguity.
  const serialized = JSON.stringify(body);
  return () => request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: serialized });
}
export const api = {
  health: (signal?: AbortSignal) => request<Schema['Health']>('/health', { signal }),
  wells: (signal?: AbortSignal) => request<Schema['WellPage']>('/wells?limit=100', { signal }),
  model: (signal?: AbortSignal) => request<Model>('/models/info', { signal }),
  sensors: (signal?: AbortSignal) => request<Schema['SensorCatalog']>('/sensors', { signal }),
  replays: (cursor?: string, signal?: AbortSignal) => request<Schema['ReplayList']>(`/replays${query({ limit: 100, cursor })}`, { signal }),
  replay: (id: string, signal?: AbortSignal) => request<Replay>(`/replays/${encodeURIComponent(id)}`, { signal }),
  events: (id: string, after: number, signal?: AbortSignal) => request<Schema['ReplayEventPage']>(`/replays/${encodeURIComponent(id)}/event-history${query({ after_sequence: after, limit: 1000 })}`, { signal }),
  evaluation: (id: string, after = 0, signal?: AbortSignal) => request<Schema['RetrospectivePage']>(`/replays/${encodeURIComponent(id)}/evaluation${query({ after_sequence: after, limit: 100 })}`, { signal }),
  alerts: (cursor?: string, signal?: AbortSignal) => request<Schema['AlertPage']>(`/alerts${query({ cursor, limit: 50 })}`, { signal }),
  telemetry: (well: string, source: string, offset: number, signal?: AbortSignal) => request<Schema['TelemetryPage']>(`/wells/${encodeURIComponent(well)}/telemetry${query({ source_instance_id: source, offset, limit: 600 })}`, { signal }),
  create: (body: Schema['CreateReplay']) => mutation<Replay>('/replays', body),
  command: (id: string, body: Schema['ReplayCommand']) => mutation<Replay>(`/replays/${encodeURIComponent(id)}/commands`, body),
};
