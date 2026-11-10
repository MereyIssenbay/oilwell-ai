import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, type Replay, type ReplayEvent } from './api/client';
import { EVENT_LIMIT, mergeEvents, score, sourceTime, streamNeedsRecovery, useReplay } from './state';

const snapshot = (state: Replay['state'] = 'running', last = 0) => ({ replay_id: 'fixture-replay', state, last_sequence: last, version: 1, cursor_position: null, alert_episode: null }) as Replay;
const flags = { schema_version: 'diagnostic-replay-1.0.0', mode: 'historical_replay', simulated_playback: true, diagnostic_only: true, accepted_for_monitoring: false } as const;
const event = (sequence: number, id = 'fixture-replay'): ReplayEvent => ({ ...flags, replay_id: id, sequence, emitted_at: '2026-11-10T00:00:00Z', event_type: 'telemetry', payload: { ...flags, timestamp: `2014-05-30T10:00:${String(sequence).padStart(2, '0')}`, source_position: sequence, sensors: { 'P-PDG': null }, source_kind: 'real', source_instance_id: 'fixture-source', well_id: 'fixture-well', time_basis: 'source_naive_assumed_utc' } });

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe('source time and evidence formatting', () => {
  it('preserves original wall-clock coordinates without local timezone conversion', () => {
    expect(sourceTime('2014-05-30T10:08:02Z')).toBe('2014-05-30 10:08:02');
    expect(sourceTime(null)).toBe('Not available');
  });
  it('does not turn missing scores or tiny thresholds into a false zero', () => {
    expect(score(null)).toBe('Unavailable'); expect(score(1e-14)).toBe('1.0000e-14'); expect(score(0)).toBe('0.00000');
  });
});
describe('bounded durable stream state', () => {
  it('deduplicates redelivery, sorts, isolates replay identities and caps memory', () => {
    const values = Array.from({ length: EVENT_LIMIT + 20 }, (_, index) => event(index + 1));
    const result = mergeEvents(values, [event(25), event(9000, 'other-replay')], 'fixture-replay');
    expect(result).toHaveLength(EVENT_LIMIT); expect(result[0].sequence).toBe(21); expect(result.at(-1)?.sequence).toBe(2020);
  });
  it('recovers missing tail even when the server snapshot is already terminal', () => {
    expect(streamNeedsRecovery(snapshot('completed', 10), 9)).toBe(true);
    expect(streamNeedsRecovery(snapshot('completed', 10), 10)).toBe(false);
    expect(streamNeedsRecovery(snapshot('paused', 10), 10)).toBe(true);
  });
  it('backfills saved history before consuming live events and ignores duplicates', async () => {
    class FakeSource {
      static instance: FakeSource;
      onopen: (() => void) | null = null; onerror: (() => void) | null = null;
      handlers = new Map<string, (event: MessageEvent) => void>();
      close = vi.fn();
      constructor(public url: string) { FakeSource.instance = this; }
      addEventListener(name: string, handler: (event: MessageEvent) => void) { this.handlers.set(name, handler); }
    }
    vi.stubGlobal('EventSource', FakeSource);
    vi.spyOn(api, 'replay').mockResolvedValue(snapshot('running', 1));
    vi.spyOn(api, 'events').mockResolvedValue({ ...flags, items: [event(1)], next_after_sequence: null });
    const { result, unmount } = renderHook(() => useReplay('fixture-replay'));
    await waitFor(() => expect(FakeSource.instance).toBeDefined());
    expect(FakeSource.instance.url).toContain('after_sequence=1');
    act(() => { FakeSource.instance.handlers.get('telemetry')!(new MessageEvent('telemetry', { data: JSON.stringify(event(2)) })); FakeSource.instance.handlers.get('telemetry')!(new MessageEvent('telemetry', { data: JSON.stringify(event(2)) })); });
    expect(result.current.events.map(e => e.sequence)).toEqual([1, 2]);
    unmount(); expect(FakeSource.instance.close).toHaveBeenCalled();
  });
  it('does not open SSE for a fully drained completed replay', async () => {
    const source = vi.fn(); vi.stubGlobal('EventSource', source);
    vi.spyOn(api, 'replay').mockResolvedValue(snapshot('completed', 1));
    vi.spyOn(api, 'events').mockResolvedValue({ ...flags, items: [event(1)], next_after_sequence: null });
    const { result } = renderHook(() => useReplay('fixture-replay'));
    await waitFor(() => expect(result.current.connection).toBe('complete'));
    expect(source).not.toHaveBeenCalled();
  });
});
