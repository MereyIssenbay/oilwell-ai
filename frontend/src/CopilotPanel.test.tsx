import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { api, ApiError, type ReplayEvent, type Schema } from './api/client';
import { CopilotPanel, ExplanationResult, safeSourceUrl } from './CopilotPanel';

// Explicitly artificial UI fixtures. The production panel never imports this module.
const explanation: Schema['Explanation'] = {
  schema_version: 'copilot-explanation-1.0.0', status: 'fallback', reason: 'deterministic_requested',
  historical_replay: true, diagnostic_only: true, accepted_for_monitoring: false,
  observations: [{ claim_id: 'obs-e1', text: 'Fixture observation: P-PDG mean is 3 Pa.', evidence_ids: ['e1'], citation_ids: [] }],
  prediction: [{ claim_id: 'pred-decision', text: 'Fixture model output remains an uncalibrated score.', evidence_ids: ['p1'], citation_ids: [] }],
  possible_interpretations: [{ claim_id: 'interpretation', text: 'Fixture context does not establish causality.', evidence_ids: [], citation_ids: ['fixture-source'] }],
  limitations: [{ claim_id: 'model-limit', text: 'Fixture diagnostic model is not accepted for monitoring.', evidence_ids: ['m1'], citation_ids: [] }],
  abstention: null,
  citations: [{ source_id: 'fixture-source', title: 'Fixture technical source', url: 'https://example.org/source', section: 'Fixture section', attribution: 'Fixture attribution', license: 'Fixture license', license_url: 'https://example.org/license', accessed_at: '2026-11-10', content: 'Fixture curated passage.', content_sha256: 'a'.repeat(64), content_kind: 'curated_paraphrase' }],
  evidence: { packet_version: 'copilot-evidence-1.0.0', model_version: 'fixture-model', event_type: 'undesirable_event', confidence: .8, abnormal_score: .8, threshold: .2, calibration: 'uncalibrated', alert_status: 'alert', episode_state: 'open', source_origin: 'real', source_time_basis: 'source_naive_assumed_utc', window_start: '2014-01-01T00:00:00', window_end: '2014-01-01T00:00:59', sample_count: 60, expected_sample_count: 60, sensors: [{ evidence_id: 'e1', sensor: 'P-PDG', unit: 'Pa', mean: 3, latest: null, trend_per_second: null, missing_fraction: .5, observed_count: 30 }], integrity: 'verified', abstention_reason: null },
  evidence_hash: 'b'.repeat(64), prompt_version: 'claim-selection-1.0.0', kb_version: 'fixture-kb', provider: 'none', provider_model: null, created_at: '2026-11-10T00:00:00Z', cached: false, usage: null,
};
const predictionEvent = (sequence = 10, replayId = 'fixture-replay') => ({
  replay_id: replayId, sequence, event_type: 'prediction', payload: { source_position: sequence + 59,
    prediction: { model_version: 'fixture-model', event_type: 'undesirable_event', provenance: { source_timestamp: '2014-01-01T00:00:59' } } },
}) as ReplayEvent;

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('does not request an explanation on mount or telemetry updates and defaults to no paid provider', async () => {
  const explain = vi.spyOn(api, 'explain').mockResolvedValue(explanation);
  const view = render(<CopilotPanel replayId="fixture-replay" events={[predictionEvent()]} />);
  view.rerender(<CopilotPanel replayId="fixture-replay" events={[predictionEvent(), predictionEvent(20)]} />);
  expect(explain).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Use optional AI provider for this request')).not.toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: 'Explain alert' }));
  await screen.findByText(explanation.observations[0].text);
  expect(explain).toHaveBeenCalledWith('fixture-replay', 10, { question: '', use_provider: false }, expect.any(AbortSignal));
  expect(screen.getByText('deterministic fallback')).toBeInTheDocument();
});

it('submits a bounded question and provider opt-in only on an explicit click', async () => {
  const explain = vi.spyOn(api, 'explain').mockResolvedValue({ ...explanation, cached: true });
  render(<CopilotPanel replayId="fixture-replay" events={[predictionEvent()]} />);
  const input = screen.getByRole('textbox', { name: 'Question about this prediction' });
  expect(input).toHaveAttribute('maxlength', '500');
  fireEvent.change(input, { target: { value: '  What evidence is available?  ' } });
  fireEvent.click(screen.getByLabelText('Use optional AI provider for this request'));
  expect(explain).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Explain alert' }));
  await screen.findByText('cached');
  expect(explain).toHaveBeenCalledWith('fixture-replay', 10, { question: 'What evidence is available?', use_provider: true }, expect.any(AbortSignal));
});

it('fills an approved question without making a provider or explanation request', () => {
  const explain = vi.spyOn(api, 'explain');
  render(<CopilotPanel replayId="fixture-replay" events={[predictionEvent()]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Show sensor trends' }));
  expect(screen.getByRole('textbox', { name: 'Question about this prediction' })).toHaveValue('Show sensor trends');
  expect(explain).not.toHaveBeenCalled();
});

it('aborts an old prediction request and ignores its late response after selection changes', async () => {
  let finish!: (value: Schema['Explanation']) => void;
  const explain = vi.spyOn(api, 'explain').mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<CopilotPanel replayId="fixture-replay" events={[predictionEvent(10), predictionEvent(20)]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Explain alert' }));
  expect(screen.getByRole('button', { name: 'Explaining…' })).toBeDisabled();
  const signal = explain.mock.calls[0][3]!;
  fireEvent.change(screen.getByLabelText('Prediction to explain'), { target: { value: '10' } });
  expect(signal.aborted).toBe(true);
  await act(async () => { finish(explanation); });
  expect(screen.queryByText(explanation.observations[0].text)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Explain alert' })).toBeEnabled();
  expect(explain).toHaveBeenCalledOnce();
});

it('isolates replay identities and exposes an empty state without fabricated evidence', () => {
  const explain = vi.spyOn(api, 'explain');
  render(<CopilotPanel replayId="different-replay" events={[predictionEvent()]} />);
  expect(screen.getByText(/Select a replay with a saved prediction/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Explain alert' })).not.toBeInTheDocument();
  expect(explain).not.toHaveBeenCalled();
});

it('shows structured request failure and allows only a deliberate retry', async () => {
  const explain = vi.spyOn(api, 'explain').mockRejectedValueOnce(new ApiError(503, 'COPILOT_UNAVAILABLE', 'Saved evidence is unavailable.', 'fixture-request')).mockResolvedValue(explanation);
  render(<CopilotPanel replayId="fixture-replay" events={[predictionEvent()]} />);
  fireEvent.click(screen.getByRole('button', { name: 'Explain alert' }));
  await screen.findByText('Saved evidence is unavailable.');
  expect(explain).toHaveBeenCalledOnce();
  expect(screen.getByRole('alert')).toHaveTextContent('fixture-request');
  fireEvent.click(screen.getByRole('button', { name: 'Explain alert' }));
  await screen.findByText(explanation.observations[0].text);
  expect(explain).toHaveBeenCalledTimes(2);
});

it('separates claim types and links evidence without navigating away from the replay route', async () => {
  const scroll = vi.fn(); Element.prototype.scrollIntoView = scroll;
  window.location.hash = '#replay';
  render(<ExplanationResult value={explanation} question="" />);
  for (const name of ['What the sensors recorded', 'What the frozen model predicted', 'Context, not a physical diagnosis', 'What this evidence cannot establish']) expect(screen.getByRole('heading', { name })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: 'Inspect evidence e1' }));
  await waitFor(() => expect(scroll).toHaveBeenCalled());
  expect(window.location.hash).toBe('#replay');
  expect(screen.getByText('e1 · P-PDG').closest('details')).toHaveAttribute('open');
  expect(screen.getByText(/Endpoint value: Unavailable/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: 'Inspect citation fixture-source' }));
  expect(screen.getByText('Fixture curated passage.').closest('details')).toHaveAttribute('open');
  expect(screen.getByRole('link', { name: 'Stored passage and provenance ↗' })).toHaveAttribute('href', '/api/copilot/sources/fixture-source');
});

it('renders unsupported answers as abstentions and treats returned text as inert text', () => {
  const unsafe = '<img src=x onerror=alert(1)>';
  render(<ExplanationResult value={{ ...explanation, status: 'abstained', reason: 'unsupported_question', abstention: 'A valve diagnosis is unsupported.', observations: [{ claim_id: 'unsafe-fixture', text: unsafe, evidence_ids: [], citation_ids: [] }], citations: [{ ...explanation.citations[0], url: 'javascript:alert(1)', license_url: 'javascript:alert(1)' }] }} question="Shut down the well" />);
  expect(screen.getByText('A valve diagnosis is unsupported.')).toBeInTheDocument();
  expect(screen.getByText(unsafe)).toBeInTheDocument();
  expect(document.querySelector('img')).toBeNull();
  expect(screen.queryByRole('link', { name: 'Original public source ↗' })).not.toBeInTheDocument();
  expect(safeSourceUrl('javascript:alert(1)')).toBeUndefined();
  expect(safeSourceUrl('http://example.org')).toBeUndefined();
});
