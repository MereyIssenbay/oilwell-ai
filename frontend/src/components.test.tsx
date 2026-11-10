import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ErrorPanel, LatestPrediction, Plot, Status } from './components';
import { ApiError } from './api/client';
const engine = vi.hoisted(() => ({ react: vi.fn(async () => ({})), purge: vi.fn(), Plots: { resize: vi.fn(async () => ({})) } }));
vi.mock('plotly.js-basic-dist-min', () => ({ default: engine }));
afterEach(() => vi.clearAllMocks());
it('presents warmup as unavailable evidence, not a normal prediction', () => {
  render(<LatestPrediction />);
  expect(screen.getByText(/requires 60 replayed rows/)).toBeInTheDocument();
  expect(screen.queryByText('100%')).not.toBeInTheDocument();
});
it('renders visible semantic status and structured error recovery', () => {
  const retry = vi.fn(); render(<><Status value="insufficient_data" /><ErrorPanel error={new ApiError(409, 'CONFLICT', 'Replay state changed', 'request-fixture')} retry={retry} /></>);
  expect(screen.getByText('insufficient data')).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('request-fixture');
  screen.getByRole('button', { name: 'Retry' }).click(); expect(retry).toHaveBeenCalledOnce();
});
it('updates Plotly without purging the mounted chart on each telemetry update', async () => {
  const observe = vi.fn(), disconnect = vi.fn();
  vi.stubGlobal('ResizeObserver', class { observe = observe; disconnect = disconnect; });
  const first = [{ x: ['2014-05-30T10:00:00'], y: [null], type: 'scatter' as const }];
  const view = render(<Plot traces={first} title="fixture-history" />);
  await waitFor(() => expect(engine.react).toHaveBeenCalledTimes(1));
  view.rerender(<Plot traces={[{ x: ['2014-05-30T10:00:01'], y: [2], type: 'scatter' }]} title="fixture-history" />);
  await waitFor(() => expect(engine.react).toHaveBeenCalledTimes(2));
  expect(engine.purge).not.toHaveBeenCalled(); expect(observe).toHaveBeenCalledTimes(1);
  view.unmount(); await act(async () => {});
  expect(engine.purge).toHaveBeenCalledTimes(1); expect(disconnect).toHaveBeenCalledOnce();
  vi.unstubAllGlobals();
});
