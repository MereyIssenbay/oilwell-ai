import { useEffect, useRef, useState } from 'react';
import { ApiError, type Replay } from './api/client';

export function useMutation(onSuccess: (value: Replay) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error>();
  const [retry, setRetry] = useState<(() => void)>();
  const mounted = useRef(true);
  const generation = useRef(0);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; generation.current += 1; }; }, []);
  async function execute(operation: () => Promise<Replay>) {
    const ticket = ++generation.current;
    const current = () => mounted.current && ticket === generation.current;
    setBusy(true); setError(undefined);
    try {
      const value = await operation();
      if (current()) { setRetry(undefined); onSuccess(value); }
    } catch (e) {
      if (current()) {
        setError(e as Error);
        setRetry(e instanceof ApiError && e.status >= 400 && e.status < 500 ? undefined : () => () => { void execute(operation); });
      }
    } finally { if (current()) setBusy(false); }
  }
  return { busy, error, retry, execute };
}
