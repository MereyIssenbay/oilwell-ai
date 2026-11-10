import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Data } from 'plotly.js';
import { api, ApiError, type Schema, type Replay, type Prediction, type Telemetry, type EpisodeEvent, type ReplayEvent } from './api/client';
import { ErrorPanel, Empty, LatestPrediction, Loading, Panel, Plot, Stat, Status } from './components';
import { CopilotPanel } from './CopilotPanel';
import { useMutation } from './mutations';
import { EVENT_LIMIT, score, sourceTime, terminal, useReplay, useResource } from './state';

const pages = [
  ['overview', 'Overview', '01'], ['wells', 'Wells & Sensor Explorer', '02'], ['replay', 'Historical Replay', '03'],
  ['alerts', 'Alerts & Event History', '04'], ['model', 'Model Information', '05'],
] as const;
type Page = typeof pages[number][0];
const currentPage = (): Page => pages.some(p => p[0] === location.hash.slice(1)) ? location.hash.slice(1) as Page : 'overview';
function storedReplay(): string | null { try { return localStorage.getItem('oilwell-replay-id'); } catch { return null; } }

export default function App() {
  const [page, setPage] = useState<Page>(currentPage);
  const [wellId, setWellId] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [sensor, setSensor] = useState('P-PDG');
  const [replayId, setReplayId] = useState<string | null>(storedReplay);
  const [listRevision, setListRevision] = useState(0);
  const [replayCursor, setReplayCursor] = useState<string>();
  const catalog = useResource(signal => Promise.all([api.wells(signal), api.model(signal), api.sensors(signal), api.health(signal)]), []);
  const sessions = useResource(signal => api.replays(replayCursor, signal), [listRevision, replayCursor]);
  const replay = useReplay(replayId);
  const wells = catalog.value?.[0].items ?? [];
  const model = catalog.value?.[1];
  const sensors = catalog.value?.[2].items ?? [];
  const health = catalog.value?.[3];
  const well = wells.find(w => w.well_id === wellId) ?? wells[0];
  const source = well?.source_instances.find(s => s.source_instance_id === sourceId) ?? well?.source_instances[0];
  const snapshot = replay.snapshot;
  const history = replay.events;
  const predictions = history.filter(e => e.event_type === 'prediction').map(e => e.payload as Prediction);
  const readings = history.filter(e => e.event_type === 'telemetry').map(e => e.payload as Telemetry);
  const episodeEvents = history.filter(e => e.event_type === 'alert_episode');
  const latestPrediction = predictions.at(-1);
  const unit = sensors.find(s => s.name === sensor)?.unit_or_domain;
  const traces = useMemo<Data[]>(() => [{ x: readings.map(r => r.timestamp), y: readings.map(r => r.sensors[sensor]), type: 'scatter', mode: 'lines', name: sensor, connectgaps: false, line: { color: '#51d5bb', width: 2 } }], [history, sensor]);
  useEffect(() => { const fn = () => setPage(currentPage()); window.addEventListener('hashchange', fn); return () => window.removeEventListener('hashchange', fn); }, []);
  useEffect(() => { if (well && well.well_id !== wellId) setWellId(well.well_id); if (source && source.source_instance_id !== sourceId) setSourceId(source.source_instance_id); }, [well, source, wellId, sourceId]);
  useEffect(() => {
    if (!replayId && sessions.value?.items.length) {
      const choice = sessions.value.items.find(s => !terminal(s.state)) ?? sessions.value.items.find(s => s.state === 'completed') ?? sessions.value.items[0];
      selectReplay(choice.replay_id);
    }
  }, [replayId, sessions.value]);
  function selectReplay(id: string) { setReplayId(id); try { localStorage.setItem('oilwell-replay-id', id); } catch { /* Storage is optional. */ } }
  function refreshed(value: Replay) { selectReplay(value.replay_id); replay.refresh(); setListRevision(v => v + 1); }
  const sensorSelect = <label className="compact-label">Sensor<select aria-label="Sensor" value={sensor} onChange={e => setSensor(e.target.value)}>{sensors.map(s => <option key={s.name} value={s.name}>{s.name} · {s.unit_or_domain}</option>)}</select></label>;
  const sessionSelect = <div className="session-select"><label>Replay session<select aria-label="Replay session" value={replayId ?? ''} onChange={e => selectReplay(e.target.value)}><option value="" disabled>Select a persisted replay</option>{replayId && !sessions.value?.items.some(s => s.replay_id === replayId) && <option value={replayId}>{replayId.slice(0, 8)} · selected session</option>}{sessions.value?.items.map(s => <option key={s.replay_id} value={s.replay_id}>{s.well_id} · {snapshot?.replay_id === s.replay_id ? snapshot.state : s.state} · {s.replay_id.slice(0, 8)}</option>)}</select></label><button className="subtle" onClick={() => { setReplayCursor(undefined); setListRevision(v => v + 1); }}>Refresh sessions</button>{sessions.value?.next_cursor && <button className="subtle" onClick={() => setReplayCursor(sessions.value!.next_cursor!)}>Older sessions</button>}</div>;
  const chart = <Panel title="Sensor telemetry" kicker="Historical source observations" action={sensorSelect}>{!replayId ? <Empty>Select a replay to view its readings.</Empty> : readings.length ? <><Plot traces={traces} title={`Replay ${replayId}: ${sensor}`} yTitle={`${sensor}${unit ? ` · ${unit}` : ''}`} /><div className="chart-footer"><span>{readings.length} retained readings · gaps represent missing values</span><span>{sourceTime(readings[0]?.timestamp)} → {sourceTime(readings.at(-1)?.timestamp)}</span></div></> : <Empty>No readings received yet. Start or resume the selected replay.</Empty>}</Panel>;
  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="#overview"><span className="brand-mark">OW<span>↗</span></span><span>OilWell <b>AI</b><small>HISTORICAL OPERATIONS</small></span></a>
      <div className="nav-heading">WORKSPACE</div><nav aria-label="Main navigation">{pages.map(([key, label, index]) => <a key={key} href={`#${key}`} className={page === key ? 'active' : ''} aria-current={page === key ? 'page' : undefined}><span className="nav-index">{index}</span>{label}<span className="nav-arrow">↗</span></a>)}</nav>
      <div className="sidebar-bottom"><span className="eyebrow">DATA ENVIRONMENT</span><strong>Petrobras 3W</strong><p>Immutable historical records.<br />Local diagnostic workspace.</p><span className="dot-label"><i />No live SCADA connection</span></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="breadcrumb">Workspace <span>/</span> {pages.find(p => p[0] === page)?.[1]}</div><div className="topbar-right"><span className="replay-badge"><i />Historical Replay</span><span className="api-indicator">API <Status value={health?.status ?? (catalog.error ? 'unavailable' : 'loading')} /></span></div></header>
      <main id="main-content"><div className="page-heading"><div><span className="eyebrow">OILWELL INTELLIGENCE / {pages.find(p => p[0] === page)?.[2]}</span><h1>{pages.find(p => p[0] === page)?.[1]}</h1><p>{page === 'overview' ? 'Explore the evidence behind every historical signal.' : page === 'wells' ? 'Inspect original sensor records without changing the source.' : page === 'replay' ? 'Replay the past. Observe predictions as source time advances.' : page === 'alerts' ? 'Trace diagnostic decisions and the episodes they create.' : 'Understand the frozen artifact, its scope and its limitations.'}</p></div><span className="workspace-label">LOCAL WORKSPACE <i /></span></div>
        <div className="diagnostic-banner"><span className="warning-icon">!</span><div><strong>Diagnostic model · rejected for monitoring</strong><span>Scores are uncalibrated. Historical playback does not represent current well conditions.</span></div><a href="#model">View model limits →</a></div>
        <ErrorPanel error={catalog.error} retry={catalog.retry} />
        {catalog.loading ? <Loading /> : <>
          {(page === 'wells' || page === 'replay') && <div className="selection-bar"><label>{page === 'replay' ? 'New replay / well' : 'Well'}<select aria-label="Well" value={well?.well_id ?? ''} onChange={e => { setWellId(e.target.value); setSourceId(''); }}>{wells.map(w => <option key={w.well_id} value={w.well_id}>{w.well_id}</option>)}</select></label><label className="instance-label">{page === 'replay' ? 'New replay / dataset instance' : 'Dataset instance'}<select aria-label="Dataset instance" value={source?.source_instance_id ?? ''} onChange={e => setSourceId(e.target.value)}>{well?.source_instances.map(s => <option key={s.source_instance_id} value={s.source_instance_id}>{s.source_start.replace('T', ' ')} · {s.row_count.toLocaleString()} rows · {s.source_instance_id.slice(-8)}</option>)}</select></label><span className="source-chip">REAL SOURCE <small>historical playback</small></span></div>}
          {page === 'overview' && <>
            <div className="stats"><Stat title="Registered wells" value={catalog.value ? wells.length : '—'} note="Approved train / validation sources" /><Stat title="Sensor channels" value={model?.sensor_names.length ?? '—'} note="Original registered sensor names" /><Stat title="Current replay" value={snapshot?.state ?? 'Not selected'} note={snapshot ? `${snapshot.well_id} · ${snapshot.speed_multiplier}× requested` : 'Choose a persisted session below'} /><Stat title="Model acceptance" value="Rejected" note="Diagnostic demonstration only" accent /></div>
            <Panel title="Replay workspace" kicker="Persisted sessions" action={<a className="button primary" href="#replay">Open replay controls ↗</a>}>{sessionSelect}<ErrorPanel error={sessions.error} retry={sessions.retry} /><ErrorPanel error={replay.error} retry={replay.refresh} />{sessions.loading && <Loading />}</Panel>
            <div className="main-grid">{chart}<Panel title="Latest prediction" kicker="Frozen model inference"><LatestPrediction value={latestPrediction} /></Panel></div>
            <Panel title="Recent episode activity" kicker="Selected replay · retained event window"><EpisodeTable events={episodeEvents.slice(-6).reverse()} /></Panel>
          </>}
          {page === 'wells' && source && well && <Explorer well={well.well_id} source={source} sensor={sensor} unit={unit} sensorSelect={sensorSelect} />}
          {page === 'replay' && <>
            <ReplayCreate key={source?.source_instance_id} sourceId={source?.source_instance_id} rowCount={source?.row_count ?? 0} onCreated={refreshed} model={model} />
            <Panel title="Replay controller" kicker="One active session at a time" action={snapshot && <Status value={snapshot.state} />}>{sessionSelect}<ErrorPanel error={sessions.error} retry={sessions.retry} /><ErrorPanel error={replay.error} retry={replay.refresh} />{snapshot ? <ReplayControls key={snapshot.replay_id} snapshot={snapshot} onChanged={refreshed} onRefresh={replay.refresh} /> : <Empty>{replayId ? 'Loading selected replay…' : 'Create a replay or select an existing session.'}</Empty>}</Panel>
            <div className="stream-bar"><span className={`stream-dot ${replay.connection === 'connected' ? 'connected' : ''}`} /><strong>{replay.connection.replaceAll('_', ' ')}</strong><span>SSE · ordered durable events</span><span className="push-right">Showing up to {EVENT_LIMIT.toLocaleString()} recent events · source timezone unverified</span></div>
            <div className="main-grid">{chart}<Panel title="Latest prediction" kicker="Uncalibrated diagnostic score"><LatestPrediction value={latestPrediction} /></Panel></div>
            <CopilotPanel key={replayId ?? 'no-replay'} replayId={replayId} events={history} />
            <Panel title="Predicted vs actual" kicker="Retrospective evaluation only"><Comparison snapshot={snapshot} /></Panel>
          </>}
          {page === 'alerts' && <Alerts sessionSelect={sessionSelect} snapshot={snapshot} events={history} error={replay.error} retry={replay.refresh} />}
          {page === 'model' && model && <ModelPage model={model} />}
        </>}
        <footer><span>OilWell AI · Historical diagnostics</span><span>No equipment control · Source timezone unverified</span></footer>
      </main>
    </div>
  </div>;
}

function Explorer({ well, source, sensor, unit, sensorSelect }: { well: string; source: Schema['WellInfo']['source_instances'][number]; sensor: string; unit?: string; sensorSelect: ReactNode }) {
  const [offset, setOffset] = useState(0);
  useEffect(() => setOffset(0), [source.source_instance_id]);
  const data = useResource(signal => api.telemetry(well, source.source_instance_id, offset, signal), [well, source.source_instance_id, offset]);
  const items = data.value?.items ?? [];
  const traces = useMemo<Data[]>(() => [{ x: items.map(r => r.timestamp), y: items.map(r => r.sensors[sensor]), type: 'scatter', mode: 'lines', name: sensor, connectgaps: false, line: { color: '#51d5bb', width: 2 } }], [data.value, sensor]);
  const missing = items.filter(r => r.sensors[sensor] == null).length;
  return <><div className="stats three"><Stat title="Instance observations" value={source.row_count.toLocaleString()} note="Original rows, before windowing" /><Stat title="Source starts" value={source.source_start.slice(0, 10)} note={sourceTime(source.source_start)} /><Stat title="Missing in displayed slice" value={items.length ? `${missing} / ${items.length}` : '—'} note={`${sensor} · null is missing, never zero`} /></div>
    <Panel title="Sensor explorer" kicker="Read-only original telemetry" action={sensorSelect}><ErrorPanel error={data.error} retry={data.retry} />{data.loading ? <Loading /> : items.length ? <Plot traces={traces} title={`${source.source_instance_id}:${sensor}`} yTitle={`${sensor} · ${unit ?? 'unit unavailable'}`} height={370} /> : <Empty>No observations in this slice.</Empty>}<div className="chart-footer"><span>Rows {offset}–{Math.max(offset, offset + items.length - 1)} · maximum 600 per page</span><div className="button-row"><button disabled={offset === 0 || data.loading} onClick={() => setOffset(v => Math.max(0, v - 600))}>Previous slice</button><button disabled={data.value?.next_offset == null || data.loading} onClick={() => setOffset(data.value!.next_offset!)}>Next slice</button></div></div></Panel>
    <Panel title="Observation details" kicker="Latest 12 rows of displayed slice"><div className="table-scroll"><table><thead><tr><th>Source timestamp</th><th>{sensor}</th><th>Availability</th></tr></thead><tbody>{items.slice(-12).map(r => <tr key={r.timestamp}><td className="mono">{sourceTime(r.timestamp)}</td><td className="mono">{r.sensors[sensor] == null ? 'Missing' : Number(r.sensors[sensor]).toPrecision(7)}</td><td><Status value={r.sensors[sensor] == null ? 'missing' : 'observed'} /></td></tr>)}</tbody></table></div></Panel></>;
}


function ReplayCreate({ sourceId, rowCount, model, onCreated }: { sourceId?: string; rowCount: number; model?: Schema['ModelInfo']; onCreated: (value: Replay) => void }) {
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [speed, setSpeed] = useState(20);
  const mutation = useMutation(onCreated);
  useEffect(() => { setStart(0); setEnd(Math.max(0, Math.min(599, rowCount - 1))); }, [sourceId, rowCount]);
  return <Panel title="Configure a replay" kicker="Source rows remain unchanged"><form className="replay-form" onSubmit={e => { e.preventDefault(); if (sourceId && model) void mutation.execute(api.create({ source_instance_id: sourceId, start_position: start, end_position: end, speed_multiplier: speed, model_version: model.model_version })); }}>
    <label>Start row<input aria-label="Start row" type="number" min={0} max={Math.max(0, rowCount - 1)} step={1} required value={start} onChange={e => setStart(Number(e.target.value))} /></label>
    <label>End row<input aria-label="End row" type="number" min={start} max={Math.max(0, rowCount - 1)} step={1} required value={end} onChange={e => setEnd(Number(e.target.value))} /></label>
    <label>Replay speed<select aria-label="Replay speed" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[.1, 1, 2, 5, 10, 20].map(s => <option key={s} value={s}>{s}×</option>)}</select></label>
    <button className="primary" disabled={mutation.busy || !sourceId || !model || end < start || start < 0 || end >= rowCount} type="submit">{mutation.busy ? 'Creating…' : 'Create replay'}</button>
  </form><ErrorPanel error={mutation.error} retry={!mutation.busy ? mutation.retry : undefined} /><p className="fineprint">Inclusive row bounds · 60 observed rows before inference · original 10-row stride · requested speed is best-effort</p></Panel>;
}

function ReplayControls({ snapshot, onChanged, onRefresh }: { snapshot: Replay; onChanged: (value: Replay) => void; onRefresh: () => void }) {
  const [speed, setSpeed] = useState(snapshot.speed_multiplier);
  useEffect(() => setSpeed(snapshot.speed_multiplier), [snapshot.replay_id, snapshot.speed_multiplier]);
  const mutation = useMutation(onChanged);
  const done = terminal(snapshot.state);
  function command(name: Schema['ReplayCommand']['command']) { void mutation.execute(api.command(snapshot.replay_id, { command: name, expected_version: snapshot.version, ...(name === 'set_speed' ? { speed_multiplier: speed } : {}) })); }
  const advanced = snapshot.cursor_position == null ? 0 : snapshot.cursor_position - snapshot.start_position + 1;
  const count = snapshot.end_position - snapshot.start_position + 1;
  return <div className="replay-control"><div className="session-meta"><span><b>{snapshot.well_id}</b> · real source</span><span className="mono">Session {snapshot.replay_id}</span></div><div className="control-buttons"><button className="primary" disabled={mutation.busy || snapshot.state !== 'created'} onClick={() => command('start')}>▶ Start</button><button disabled={mutation.busy || snapshot.state !== 'running'} onClick={() => command('pause')}>Ⅱ Pause</button><button disabled={mutation.busy || snapshot.state !== 'paused'} onClick={() => command('resume')}>▶ Resume</button><button className="danger-outline" disabled={mutation.busy || done} onClick={() => command('stop')}>■ Stop</button><label>Playback speed<select aria-label="Playback speed" value={speed} disabled={done || mutation.busy} onChange={e => setSpeed(Number(e.target.value))}>{[.1, 1, 2, 5, 10, 20].map(s => <option key={s} value={s}>{s}×</option>)}</select></label><button disabled={done || mutation.busy || speed === snapshot.speed_multiplier} onClick={() => command('set_speed')}>Apply speed</button></div><ErrorPanel error={mutation.error} retry={!mutation.busy ? mutation.retry : undefined} />{mutation.error instanceof ApiError && mutation.error.status === 409 && <p className="notice">Session state changed or the command conflicts. Refresh the selected replay state before issuing a new command. <button onClick={onRefresh}>Refresh replay state</button></p>}<div className="progress-label"><span>{advanced.toLocaleString()} / {count.toLocaleString()} source rows</span><span>{(100 * advanced / count).toFixed(1)}%</span></div><progress value={advanced} max={count} aria-label="Replay progress" /><div className="chart-footer"><span>Current source time: <b>{sourceTime(snapshot.cursor_timestamp)}</b></span><span>Open episode: {snapshot.alert_episode ? <Status value="alert" /> : 'None'}</span></div>{snapshot.failure && <div role="alert" className="error-panel">{snapshot.failure.message} · {snapshot.failure.code}</div>}</div>;
}

function Comparison({ snapshot }: { snapshot?: Replay }) {
  const [after, setAfter] = useState(0);
  useEffect(() => setAfter(0), [snapshot?.replay_id]);
  const data = useResource(signal => snapshot?.state === 'completed' ? api.evaluation(snapshot.replay_id, after, signal) : Promise.resolve(null), [snapshot?.replay_id, snapshot?.state, after]);
  const rows = data.value?.items ?? [];
  const traces = useMemo<Data[]>(() => [
    { x: rows.map(r => r.timestamp), y: rows.map(r => r.predicted_event_type === 'unknown' ? null : Number(r.predicted_event_type === 'undesirable_event')), type: 'scatter', mode: 'lines+markers', name: 'Predicted binary event', connectgaps: false, line: { color: '#eead58', shape: 'hv', width: 2 }, marker: { size: 5 } },
    { x: rows.map(r => r.timestamp), y: rows.map(r => r.actual_binary), type: 'scatter', mode: 'lines+markers', name: 'Ground truth · retrospective', connectgaps: false, line: { color: '#8a9ff0', shape: 'hv', width: 2, dash: 'dot' }, marker: { size: 4 } },
  ], [data.value]);
  if (snapshot?.state !== 'completed') return <Empty>Ground truth is available only after this replay completes. Original labels are excluded from inference and the live playback stream.</Empty>;
  return <><div className="notice">Retrospective labels · original class/state joined after completion. This development example is not an independent benchmark.</div><ErrorPanel error={data.error} retry={data.retry} />{data.loading ? <Loading /> : rows.length ? <><Plot traces={traces} title={`Retrospective ${snapshot.replay_id}`} height={260} binary /><div className="table-scroll"><table><thead><tr><th>Source time / row</th><th>Prediction</th><th>Actual event</th><th>Comparison</th></tr></thead><tbody>{rows.map(r => <tr key={r.prediction_id}><td className="mono">{sourceTime(r.timestamp)}<small>Row {r.source_position}</small></td><td>{r.predicted_event_type.replaceAll('_', ' ')}<small>Score {score(r.abnormal_score)}</small></td><td>{r.actual_event_name?.replaceAll('_', ' ') ?? 'Unknown label'}<small>Class {r.raw_class ?? 'null'} · {r.actual_phase}</small></td><td><Status value={r.decision_matches === null ? 'unavailable' : r.decision_matches ? 'match' : 'mismatch'} /></td></tr>)}</tbody></table></div><div className="chart-footer"><span>{rows.length} prediction endpoints on this page · not continuous event duration</span><button disabled={data.value?.next_after_sequence == null} onClick={() => setAfter(data.value!.next_after_sequence!)}>Next comparison page</button>{after > 0 && <button onClick={() => setAfter(0)}>First page</button>}</div></> : <Empty>This completed replay has no prediction windows.</Empty>}</>;
}

function EpisodeTable({ events }: { events: ReplayEvent[] }) {
  if (!events.length) return <Empty>No episode transitions in the displayed event window.</Empty>;
  return <div className="table-scroll"><table><thead><tr><th>Source time</th><th>Diagnostic status</th><th>Episode</th><th>Source row</th></tr></thead><tbody>{events.map(e => { const p = e.payload as EpisodeEvent; return <tr key={e.sequence}><td className="mono">{sourceTime(p.timestamp)}</td><td><Status value={p.transition} /></td><td className="mono">{p.episode_id.slice(0, 8)}<small>{p.transition === 'opened' ? 'New diagnostic episode' : p.transition === 'resolved' ? 'Resolved by normal prediction' : 'Existing episode update'}</small></td><td>{p.source_position}</td></tr>; })}</tbody></table></div>;
}
function Alerts({ sessionSelect, snapshot, events, error, retry }: { sessionSelect: ReactNode; snapshot?: Replay; events: ReplayEvent[]; error?: Error; retry: () => void }) {
  const [cursor, setCursor] = useState<string>();
  const synchronous = useResource(signal => api.alerts(cursor, signal), [cursor]);
  const episodes = events.filter(e => e.event_type === 'alert_episode');
  const openings = episodes.filter(e => (e.payload as EpisodeEvent).transition === 'opened').length;
  return <><Panel title="Replay episode history" kicker="Diagnostic severity · not physical risk">{sessionSelect}<ErrorPanel error={error} retry={retry} /><div className="stats three"><Stat title="Open episode now" value={snapshot?.alert_episode ? 'Active' : snapshot ? 'None' : '—'} note="Abstention does not resolve an episode" accent={!!snapshot?.alert_episode} /><Stat title="Openings in retained window" value={openings} note={`Among ${events.length} retained events; not lifetime total`} /><Stat title="Episode transitions in window" value={episodes.length} note="Updates and resolutions are not new alerts" /></div><EpisodeTable events={[...episodes].reverse()} /></Panel>
    <Panel title="Event timeline" kicker={`Selected replay · most recent ${Math.min(100, events.length)} retained events`}><div className="timeline">{events.length ? [...events].reverse().slice(0, 100).map(e => <div className="timeline-row" key={e.sequence}><span className={`timeline-dot ${e.event_type}`} /><span className="mono">#{e.sequence}</span><strong>{e.event_type.replaceAll('_', ' ')}</strong><span>{eventTime(e)}</span><small>{e.event_type === 'telemetry' ? 'Original sensor reading' : e.event_type === 'prediction' ? (e.payload as Prediction).prediction.event_type.replaceAll('_', ' ') : 'Persisted replay event'}</small></div>) : <Empty>Select a replay to inspect its ordered history.</Empty>}</div></Panel>
    <Panel title="Synchronous diagnostic detections" kicker="Separate /predict history · not replay episodes"><ErrorPanel error={synchronous.error} retry={synchronous.retry} />{synchronous.loading ? <Loading /> : synchronous.value?.items.length ? <div className="table-scroll"><table><thead><tr><th>Well / source time</th><th>Status</th><th>Abnormal score</th><th>Prediction ID</th></tr></thead><tbody>{synchronous.value.items.map(a => <tr key={a.alert_id}><td>{a.well_id}<small>{sourceTime(a.timestamp)}</small></td><td><Status value="diagnostic_detection" /></td><td className="mono">{score(a.abnormal_score)}</td><td className="mono">{a.prediction_id.slice(0, 12)}</td></tr>)}</tbody></table></div> : <Empty>No synchronous detections on this page.</Empty>}<div className="chart-footer"><span>Up to 50 persisted detections per page</span><button disabled={!synchronous.value?.next_cursor} onClick={() => setCursor(synchronous.value!.next_cursor!)}>Next detections</button>{cursor && <button onClick={() => setCursor(undefined)}>First page</button>}</div></Panel></>;
}
function eventTime(event: ReplayEvent): string {
  if (event.event_type === 'telemetry') return sourceTime((event.payload as Telemetry).timestamp);
  if (event.event_type === 'prediction') return sourceTime((event.payload as Prediction).prediction.provenance.source_timestamp);
  if (event.event_type === 'alert_episode') return sourceTime((event.payload as EpisodeEvent).timestamp);
  return `Processed ${sourceTime(event.emitted_at)} UTC`;
}
function ModelPage({ model }: { model: Schema['ModelInfo'] }) {
  return <><div className="stats three"><Stat title="Monitoring acceptance" value="Rejected" note="Artifact is retained for diagnostics" accent /><Stat title="Calibration" value={model.calibration} note="Probability scores are uncalibrated" /><Stat title="Causal feature window" value={`${model.window_rows} rows`} note={`A prediction every ${model.stride_rows} source rows`} /></div><Panel title="Frozen model registry" kicker="Artifact identity" action={<Status value="rejected" />}><dl className="model-details"><div><dt>Model version</dt><dd className="mono">{model.model_version}</dd></div><div><dt>Prediction task</dt><dd>{model.task.replaceAll('_', ' ')}</dd></div><div><dt>Supported labels</dt><dd>{model.supported_labels.join(' / ')}</dd></div><div><dt>Alert threshold</dt><dd className="mono">Score ≥ {model.threshold.toString()}</dd></div><div><dt>Preprocessor fingerprint</dt><dd className="mono hash">{model.preprocessor_fingerprint}</dd></div><div><dt>Model artifact SHA-256</dt><dd className="mono hash">{model.model_artifact_sha256}</dd></div></dl></Panel><div className="two-grid"><Panel title="Known limitations" kicker="Read before interpreting predictions"><ul className="limitations">{model.limitations.map(l => <li key={l}>{l}</li>)}</ul></Panel><Panel title="Registered input channels" kicker={`${model.sensor_names.length} sensors · labels excluded`}><div className="sensor-tags">{model.sensor_names.map(s => <span key={s}>{s}</span>)}</div><p className="fineprint">Original class and auxiliary state are targets, never input features. Registered ESTADO-* channels are source sensors.</p></Panel></div></>;
}
