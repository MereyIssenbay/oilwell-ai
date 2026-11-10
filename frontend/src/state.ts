import { useEffect, useState } from 'react';
import { api, type Replay, type ReplayEvent } from './api/client';

export const EVENT_LIMIT = 2000;
export const terminal = (state: Replay['state']) => ['completed', 'stopped', 'failed'].includes(state);
export const streamNeedsRecovery = (snapshot: Replay, watermark: number) => !terminal(snapshot.state) || watermark < snapshot.last_sequence;
export function mergeEvents(previous: ReplayEvent[], incoming: ReplayEvent[], replayId: string): ReplayEvent[] {
  const map = new Map(previous.filter(e => e.replay_id === replayId).map(e => [e.sequence, e]));
  incoming.forEach(e => { if (e.replay_id === replayId) map.set(e.sequence, e); });
  return [...map.values()].sort((a, b) => a.sequence - b.sequence).slice(-EVENT_LIMIT);
}
export function sourceTime(value: string | null | undefined): string {
  return value ? value.replace('T', ' ').replace(/Z$/, '').replace(/\+00:00$/, '') : 'Not available';
}
export function score(value: number | null | undefined): string {
  if (value == null) return 'Unavailable';
  return value > 0 && value < .0001 ? value.toExponential(4) : value.toPrecision(6);
}
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, dependencies: unknown[]) {
  const [value, setValue] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setValue(undefined); setError(undefined);
    load(controller.signal).then(result => { if (!controller.signal.aborted) setValue(result); })
      .catch(e => { if (!controller.signal.aborted) setError(e); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  // Dependencies are explicit call-site request identity plus a retry revision.
  }, [...dependencies, revision]);
  return { value, error, loading, retry: () => setRevision(v => v + 1) };
}

export function useReplay(id: string | null) {
  const [snapshot, setSnapshot] = useState<Replay>();
  const [events, setEvents] = useState<ReplayEvent[]>([]);
  const [connection, setConnection] = useState('idle');
  const [error, setError] = useState<Error>();
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    setSnapshot(undefined); setEvents([]); setError(undefined);
    if (!id) { setConnection('idle'); return; }
    const controller = new AbortController();
    let stream: EventSource | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let watermark = 0;
    let initialized = false;
    let current: Replay | undefined;
    let disposed = false;
    const accept = (event: ReplayEvent) => {
      if (event.replay_id !== id || event.mode !== 'historical_replay' || !Number.isSafeInteger(event.sequence)) throw new Error('Invalid replay event identity.');
      if (event.sequence <= watermark) return;
      if (event.sequence !== watermark + 1) throw new Error('Replay sequence gap; recovering durable history.');
      watermark = event.sequence;
      setEvents(old => mergeEvents(old, [event], id));
      if (event.event_type === 'replay_state') {
        current = event.payload as Replay;
        setSnapshot(current);
        if (terminal(current.state)) { stream?.close(); setConnection('complete'); }
      } else if (event.event_type === 'telemetry') {
        const value = event.payload as import('./api/client').Telemetry;
        setSnapshot(old => old ? { ...old, cursor_position: value.source_position, cursor_timestamp: value.timestamp, last_sequence: event.sequence } : old);
      } else if (event.event_type === 'prediction') {
        const value = event.payload as import('./api/client').Prediction;
        setSnapshot(old => old ? { ...old, alert_episode: value.alert_episode, last_sequence: event.sequence } : old);
      }
    };
    const schedule = (e?: Error) => {
      stream?.close();
      if (disposed) return;
      if (e) setError(e);
      setConnection('reconnecting');
      clearTimeout(timer); timer = setTimeout(connect, 1800);
    };
    const connect = async () => {
      if (disposed) return;
      setConnection(initialized ? 'reconnecting' : 'loading');
      try {
        current = await api.replay(id, controller.signal);
        if (disposed) return;
        setSnapshot(current);
        if (!initialized) watermark = Math.max(0, current.last_sequence - EVENT_LIMIT);
        let more = true;
        while (more && !disposed) {
          const page = await api.events(id, watermark, controller.signal);
          page.items.forEach(accept);
          more = page.next_after_sequence != null;
        }
        initialized = true; setError(undefined);
        // Refresh state after backfill so older history does not overwrite a newer snapshot.
        current = await api.replay(id, controller.signal);
        if (disposed) return;
        setSnapshot(current);
        if (terminal(current.state) && watermark >= current.last_sequence) { setConnection('complete'); return; }
        stream = new EventSource(`/api/replays/${encodeURIComponent(id)}/events?after_sequence=${watermark}`);
        stream.onopen = () => { if (!disposed) { setConnection('connected'); setError(undefined); } };
        for (const kind of ['replay_state', 'telemetry', 'prediction', 'alert_episode', 'replay_error']) {
          stream.addEventListener(kind, raw => {
            if (disposed) return;
            try { accept(JSON.parse((raw as MessageEvent).data) as ReplayEvent); }
            catch (e) { schedule(e as Error); }
          });
        }
        stream.addEventListener('stream_error', () => schedule(new Error('Stream interrupted; reconnecting from the last durable event.')));
        stream.onerror = () => { if (!disposed && current && streamNeedsRecovery(current, watermark)) schedule(new Error('Stream disconnected. Saved observations remain visible.')); };
      } catch (e) { if (!disposed) schedule(e as Error); }
    };
    void connect();
    return () => { disposed = true; controller.abort(); stream?.close(); clearTimeout(timer); };
  }, [id, revision]);
  return { snapshot, events, connection, error, refresh: () => setRevision(v => v + 1), setSnapshot };
}
