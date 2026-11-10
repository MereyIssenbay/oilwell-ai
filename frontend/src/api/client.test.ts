import { afterEach, expect, it, vi } from 'vitest';
import { ApiError, mutation, request } from './client';
afterEach(() => vi.unstubAllGlobals());
it('retains identical mutation payload and idempotency key across retries', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ state: 'created' }), { status: 200 }));
  // Each call must return a fresh response body, like a real network request.
  fetch.mockImplementation(async () => new Response(JSON.stringify({ state: 'created' }), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  const retry = mutation('/replays', { source_instance_id: 'fixture-source', start_position: 0 }, 'fixture-key');
  await retry(); await retry();
  expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe('fixture-key');
  expect(fetch.mock.calls[1][1].body).toBe(fetch.mock.calls[0][1].body);
  expect(fetch.mock.calls[1][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[0][1].headers['Idempotency-Key']);
});
it('preserves sanitized structured API error identity', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ error: { code: 'REPLAY_VERSION_CONFLICT', message: 'Replay version changed', request_id: 'fixture-request' } }), { status: 409 })));
  await expect(request('/replays/fixture')).rejects.toMatchObject({ status: 409, code: 'REPLAY_VERSION_CONFLICT', requestId: 'fixture-request' });
});
it('shows a connection error without exposing underlying transport details', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private transport configuration')));
  await expect(request('/health')).rejects.toMatchObject({ code: 'CONNECTION_UNAVAILABLE', status: 0 });
  try { await request('/health'); } catch (error) { expect((error as ApiError).message).not.toContain('private'); }
});
it('rejects unreadable responses rather than inventing data', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>not JSON</html>', { status: 200 })));
  await expect(request('/wells')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
});
