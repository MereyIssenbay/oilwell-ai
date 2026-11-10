import { useEffect, useId, useRef, useState } from 'react';
import { api, type Prediction, type ReplayEvent, type Schema } from './api/client';
import { Empty, ErrorPanel, Loading, Panel, Status } from './components';
import { sourceTime } from './state';

/** Only persisted prediction coordinates leave the browser; sensor evidence is assembled server-side. */
export function CopilotPanel({ replayId, events }: { replayId: string | null; events: ReplayEvent[] }) {
  const predictions = events.filter(event => event.replay_id === replayId && event.event_type === 'prediction').slice(-50).reverse();
  const latest = predictions[0];
  const [pinned, setPinned] = useState<ReplayEvent>();
  const selected = pinned?.replay_id === replayId ? pinned : latest;
  const choices = selected && !predictions.some(event => event.sequence === selected.sequence)
    ? [selected, ...predictions] : predictions;
  useEffect(() => { if (!pinned && latest) setPinned(latest); }, [latest, pinned]);
  return <Panel title="Alert evidence copilot" kicker="Historical Replay · read-only explanation" className="copilot-panel" action={<Status value="evidence_grounded" />}>
    {!replayId || !selected ? <><Empty>Select a replay with a saved prediction to inspect its evidence.</Empty><p className="copilot-empty-note">The copilot does not run inference or use retrospective ground-truth labels.</p></> : <div className="copilot-body">
      <p className="copilot-intro">Explore what the model observed at a saved prediction. Sensor observations, model output and possible interpretations remain separate. Explanations do not establish a physical diagnosis.</p>
      <div className="copilot-selection"><label>Prediction to explain<select aria-label="Prediction to explain" value={selected.sequence} onChange={event => setPinned(choices.find(value => value.sequence === Number(event.target.value)))}>{choices.map(event => {
        const value = event.payload as Prediction;
        return <option key={event.sequence} value={event.sequence}>Row {value.source_position} · {sourceTime(value.prediction.provenance.source_timestamp)} · {value.prediction.event_type.replaceAll('_', ' ')}</option>;
      })}</select></label><button disabled={!latest || latest.sequence === selected.sequence} onClick={() => setPinned(latest)}>Use latest prediction</button></div>
      <PredictionExplanation key={`${replayId}:${selected.sequence}`} replayId={replayId} event={selected} />
    </div>}
  </Panel>;
}

function PredictionExplanation({ replayId, event }: { replayId: string; event: ReplayEvent }) {
  const value = event.payload as Prediction;
  const [question, setQuestion] = useState('');
  const [useProvider, setUseProvider] = useState(false);
  const [result, setResult] = useState<Schema['Explanation']>();
  const [asked, setAsked] = useState('');
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => { active.current?.abort(); }, []);
  async function explain() {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true); setError(undefined); setResult(undefined);
    const submitted = question.trim();
    setAsked(submitted);
    try {
      const explanation = await api.explain(replayId, event.sequence, { question: submitted, use_provider: useProvider }, controller.signal);
      if (!controller.signal.aborted) setResult(explanation);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure : new Error('Explanation unavailable.'));
    } finally {
      if (!controller.signal.aborted) { setBusy(false); active.current = null; }
    }
  }
  return <>
    <div className="copilot-context"><span>Saved event #{event.sequence} · source row {value.source_position}</span><span className="mono">{value.prediction.model_version}</span><span>Uncalibrated · rejected for monitoring</span></div>
    <form className="copilot-form" onSubmit={event => { event.preventDefault(); void explain(); }}>
      <label>Question about this prediction<textarea aria-label="Question about this prediction" placeholder="What did the model observe? Leave blank for an evidence summary." maxLength={500} value={question} disabled={busy} onChange={event => setQuestion(event.target.value)} /></label>
      <span className="copilot-count">{question.length} / 500</span>
      <div className="copilot-prompts" aria-label="Suggested evidence questions">{['Show sensor trends', 'What data is missing', 'Explain the score'].map(prompt => <button key={prompt} type="button" disabled={busy} onClick={() => setQuestion(prompt)}>{prompt}</button>)}</div>
      <div className="copilot-form-footer"><label className="copilot-provider"><input type="checkbox" checked={useProvider} disabled={busy} onChange={event => setUseProvider(event.target.checked)} />Use optional AI provider for this request</label><button className="primary" type="submit" disabled={busy}>{busy ? 'Explaining…' : 'Explain alert'}</button></div>
      <p className="fineprint">Default: deterministic summary, no API charge. Optional AI uses the server budget and falls back when unavailable. No automatic requests or equipment controls.</p>
    </form>
    <div aria-live="polite" aria-busy={busy}>
      {busy && <Loading>Checking saved evidence…</Loading>}
      <ErrorPanel error={error} />
      {error && <p className="fineprint">Submit again to retry this saved prediction. No explanation is shown for a failed request.</p>}
      {result && <ExplanationResult value={result} question={asked} />}
    </div>
  </>;
}

const reasonText: Record<Schema['Explanation']['reason'], string> = {
  deterministic_requested: 'Deterministic summary requested. No provider call needed.',
  provider_disabled: 'AI provider is disabled. Showing the deterministic summary.',
  provider_unavailable: 'AI provider could not respond. Showing the deterministic summary.',
  provider_invalid: 'The provider response failed grounding checks. Showing verified evidence only.',
  budget_exhausted: 'Server request budget reached. Showing the deterministic summary.',
  unsupported_question: 'This question cannot be answered from the approved evidence.',
  missing_evidence: 'Available evidence is insufficient for an explanation.',
  conflicting_evidence: 'Evidence conflicts prevent a reliable explanation.',
  provider_refusal: 'The provider abstained. No unsupported interpretation is supplied.',
  provider_selected: 'AI selected from verified claims. Values and citations come from saved evidence.',
};

export function safeSourceUrl(value: string): string | undefined {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : undefined; } catch { return undefined; }
}

function evidenceValue(value: number | null) { return value == null ? 'Unavailable' : String(value); }

export function ExplanationResult({ value, question }: { value: Schema['Explanation']; question: string }) {
  const prefix = useId().replaceAll(':', '');
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const packet = value.evidence;
  const evidenceIds = new Set(['p1', 'm1', 'w1', 'r1', 'h1', ...packet.sensors.map(sensor => sensor.evidence_id)]);
  function claims(items: Schema['Claim'][]) {
    return items.length ? <ul className="copilot-claims">{items.map(claim => <li key={claim.claim_id}>{claim.text}<div className="copilot-refs">
      {claim.evidence_ids.map(id => evidenceIds.has(id) ? <a key={`evidence-${id}`} href={`#${prefix}-evidence-${id}`} onClick={event => reveal(event, `${prefix}-evidence-${id}`, setEvidenceOpen)} aria-label={`Inspect evidence ${id}`}>Evidence {id}</a> : <span key={`evidence-${id}`}>Evidence unavailable</span>)}
      {(claim.citation_ids ?? []).map(id => value.citations.some(source => source.source_id === id) ? <a key={`citation-${id}`} href={`#${prefix}-source-${id}`} onClick={event => reveal(event, `${prefix}-source-${id}`, setSourcesOpen)} aria-label={`Inspect citation ${id}`}>Source {id}</a> : <span key={`citation-${id}`}>Citation unavailable</span>)}
    </div></li>)}</ul> : <p>No supported claims in this category.</p>;
  }
  function reveal(event: React.MouseEvent<HTMLAnchorElement>, id: string, expand: (open: boolean) => void) {
    // Hashes select dashboard pages, so in-panel references must not change the route.
    event.preventDefault(); expand(true);
    requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'nearest' }));
  }
  return <div className="copilot-result">
    <div className="copilot-result-meta"><Status value={value.status === 'provider' ? 'provider_selected' : value.status === 'fallback' ? 'deterministic_fallback' : 'abstained'} /><Status value={value.cached ? 'cached' : 'new_summary'} /><small>{value.provider_model ? `Provider: ${value.provider_model}` : 'No AI provider output'}</small></div>
    {question && <p className="notice">Question: {question}</p>}
    <p className="copilot-intro">{reasonText[value.reason]}</p>
    {value.abstention && <div className="copilot-abstention" role="status"><strong>Insufficient support for the requested conclusion</strong>{value.abstention}</div>}
    <div className="copilot-columns">
      <section className="copilot-section"><span className="eyebrow">01 / OBSERVATION</span><h3>What the sensors recorded</h3>{claims(value.observations)}</section>
      <section className="copilot-section"><span className="eyebrow">02 / PREDICTION</span><h3>What the frozen model predicted</h3>{claims(value.prediction)}</section>
      <section className="copilot-section"><span className="eyebrow">03 / POSSIBLE INTERPRETATION</span><h3>Context, not a physical diagnosis</h3>{claims(value.possible_interpretations)}</section>
      <section className="copilot-section"><span className="eyebrow">04 / LIMITATIONS</span><h3>What this evidence cannot establish</h3>{claims(value.limitations)}</section>
    </div>
    <details className="copilot-references" open={evidenceOpen} onToggle={event => setEvidenceOpen(event.currentTarget.open)}><summary>Inspect evidence · {packet.sensors.length} sensor channels and saved model output</summary>
      <ul className="copilot-reference-list">
        <li id={`${prefix}-evidence-p1`}><strong>p1 · Prediction output</strong><p>Event: {packet.event_type.replaceAll('_', ' ')} · Alert status: {packet.alert_status.replaceAll('_', ' ')}</p><p className="copilot-evidence-value">Selected-class confidence: {evidenceValue(packet.confidence)}<br />Abnormal score: {evidenceValue(packet.abnormal_score)}<br />Frozen threshold: {packet.threshold}</p><small>Calibration: {packet.calibration}. Scores are not certainty or proof of a physical event.</small></li>
        <li id={`${prefix}-evidence-m1`}><strong>m1 · Model identity</strong><p className="mono">{packet.model_version}</p><small>Diagnostic only · rejected for monitoring.</small></li>
        <li id={`${prefix}-evidence-w1`}><strong>w1 · Causal observation window</strong><p>{sourceTime(packet.window_start)} → {sourceTime(packet.window_end)}</p><small>{packet.sample_count} / {packet.expected_sample_count} expected rows · original source clock, timezone unverified.</small></li>
        <li id={`${prefix}-evidence-r1`}><strong>r1 · Episode at prediction time</strong><p>{packet.episode_state.replaceAll('_', ' ')}</p><small>Captured with this prediction; later episode outcomes are excluded.</small></li>
        <li id={`${prefix}-evidence-h1`}><strong>h1 · Historical playback</strong><p>Original dataset origin: {packet.source_origin}.</p><small>Historical Replay · no live SCADA connection.</small></li>
        {packet.sensors.map(sensor => <li key={sensor.evidence_id} id={`${prefix}-evidence-${sensor.evidence_id}`}><strong>{sensor.evidence_id} · {sensor.sensor}</strong><p className="copilot-evidence-value">Mean: {evidenceValue(sensor.mean)} · Endpoint value: {evidenceValue(sensor.latest)}<br />Trend per second: {evidenceValue(sensor.trend_per_second)}</p><small>Unit/domain: {sensor.unit ?? 'Unspecified'} · {sensor.observed_count} observed rows · missing fraction: {sensor.missing_fraction}. Trend is a descriptive OLS slope, not physical causality.</small></li>)}
      </ul>
    </details>
    <details className="copilot-references" open={sourcesOpen} onToggle={event => setSourcesOpen(event.currentTarget.open)}><summary>Cited technical sources · {value.citations.length} retrieved passages</summary>
      <ul className="copilot-reference-list">{value.citations.map(source => <li key={source.source_id} id={`${prefix}-source-${source.source_id}`}><strong>{source.title}</strong><p>{source.section}</p><blockquote>{source.content}</blockquote><small>Curated paraphrase · {source.attribution} · {source.license}</small><p><a href={`/api/copilot/sources/${encodeURIComponent(source.source_id)}`} target="_blank" rel="noopener noreferrer">Stored passage and provenance ↗</a>{safeSourceUrl(source.url) && <> · <a href={safeSourceUrl(source.url)} target="_blank" rel="noopener noreferrer">Original public source ↗</a></>}{safeSourceUrl(source.license_url) && <> · <a href={safeSourceUrl(source.license_url)} target="_blank" rel="noopener noreferrer">License ↗</a></>}</p><small className="mono">Passage SHA-256: {source.content_sha256}</small></li>)}</ul>
      {!value.citations.length && <p className="copilot-empty-note">No technical source was retrieved for this answer.</p>}
    </details>
    <p className="copilot-model">Evidence SHA-256: {value.evidence_hash}<br />Knowledge base: {value.kb_version} · {value.prompt_version} · generated {sourceTime(value.created_at)} UTC</p>
    <p className="fineprint">Read-only historical explanation. No operational procedure or equipment command is generated.</p>
  </div>;
}
