import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ApiError, type Replay } from './api/client';
import { useMutation } from './mutations';

it('ignores an old identity mutation completing after unmount', async () => {
  let finish!: (value: Replay) => void;
  const operation = () => new Promise<Replay>(resolve => { finish = resolve; });
  const success = vi.fn();
  const { result, unmount } = renderHook(() => useMutation(success));
  act(() => { void result.current.execute(operation); });
  unmount();
  await act(async () => finish({ replay_id: 'old-session' } as Replay));
  expect(success).not.toHaveBeenCalled();
});
it('retains ambiguous transport retry operation but not a known version conflict', async () => {
  const { result } = renderHook(() => useMutation(vi.fn()));
  const operation = vi.fn().mockRejectedValue(new ApiError(0, 'NETWORK', 'Connection unavailable'));
  await act(async () => { await result.current.execute(operation); });
  expect(result.current.retry).toBeTypeOf('function');
  await act(async () => { await result.current.execute(async () => { throw new ApiError(409, 'REPLAY_VERSION_CONFLICT', 'Refresh state'); }); });
  expect(result.current.retry).toBeUndefined();
  expect(result.current.error).toMatchObject({ status: 409 });
});
