import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Data, Layout } from 'plotly.js';
import { ApiError, type Prediction } from './api/client';
import { score, sourceTime } from './state';

export function Status({ value }: { value: string }) {
  const tone = ['alert', 'opened', 'failed', 'rejected', 'degraded'].includes(value) ? 'warning' : ['running', 'connected', 'completed', 'ready', 'normal', 'resolved', 'ok'].includes(value) ? 'good' : 'muted';
  return <span className={`status ${tone}`}><i />{value.replaceAll('_', ' ')}</span>;
}
export function ErrorPanel({ error, retry }: { error?: Error; retry?: () => void }) {
  if (!error) return null;
  return <div className="error-panel" role="alert"><div><strong>Unable to complete request</strong><p>{error.message}</p>{error instanceof ApiError && <small>{error.code}{error.requestId && ` · Request ${error.requestId}`}</small>}</div>{retry && <button onClick={retry}>Retry</button>}</div>;
}
export function Empty({ children }: { children: ReactNode }) { return <div className="empty">{children}</div>; }
export function Loading({ children = 'Loading historical records…' }: { children?: ReactNode }) { return <div className="loading" role="status"><span className="spinner" />{children}</div>; }
export function Panel({ title, kicker, action, children, className = '' }: { title: string; kicker?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-head"><div>{kicker && <span className="eyebrow">{kicker}</span>}<h2>{title}</h2></div>{action}</div>{children}</section>;
}
export function Stat({ title, value, note, accent }: { title: string; value: ReactNode; note: string; accent?: boolean }) {
  return <div className={`stat ${accent ? 'accent' : ''}`}><span>{title}</span><strong>{value}</strong><small>{note}</small></div>;
}
export function Plot({ traces, title, yTitle, height = 310, binary = false }: { traces: Data[]; title: string; yTitle?: string; height?: number; binary?: boolean }) {
  const element = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string>();
  const [ready, setReady] = useState(false);
  const engine = useRef<typeof import('plotly.js') | null>(null);
  const serial = useRef<Promise<unknown>>(Promise.resolve());
  const revision = useRef(0);
  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | undefined;
    let cleanup: (() => void) | undefined;
    import('plotly.js-basic-dist-min').then(({ default: Plotly }) => {
      if (cancelled || !element.current) return;
      const node = element.current;
      engine.current = Plotly;
      setReady(true);
      observer = new ResizeObserver(() => { void serial.current.then(() => { if (!cancelled) return Plotly.Plots.resize(node); }).catch(() => {}); });
      observer.observe(node);
      cleanup = () => { engine.current = null; void serial.current.finally(() => Plotly.purge(node)); };
    }).catch(() => { if (!cancelled) setError('Chart module unavailable. Retry this page.'); });
    return () => { cancelled = true; observer?.disconnect(); cleanup?.(); };
  }, []);
  useEffect(() => {
    if (!ready || !engine.current || !element.current) return;
    const Plotly = engine.current;
    const node = element.current;
    const token = ++revision.current;
    const layout: Partial<Layout> = {
        autosize: true, height, paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
        font: { family: 'Inter, Segoe UI, sans-serif', color: '#98a7b9', size: 11 },
        margin: { l: 65, r: 20, t: binary ? 65 : 20, b: 62 }, hovermode: 'x unified',
        xaxis: { type: 'date', gridcolor: '#26303c', zeroline: false, tickformat: '%H:%M:%S', title: { text: 'Original source time · timezone unverified', font: { size: 10 } } },
        yaxis: { gridcolor: '#26303c', zeroline: false, title: { text: yTitle ?? '' }, ...(binary ? { range: [-.1, 1.1], tickvals: [0, 1], ticktext: ['Normal', 'Undesirable'] } : {}) },
        legend: { orientation: 'h', x: 0, y: 1.06, yanchor: 'bottom', font: { size: 10 } },
        hoverlabel: { bgcolor: '#202a36', bordercolor: '#45505f', font: { color: '#e9edf3' } },
        uirevision: title,
      };
    serial.current = serial.current.then(() => {
      if (token !== revision.current || engine.current !== Plotly) return;
      return Plotly.react(node, traces, layout, { responsive: true, displaylogo: false, displayModeBar: 'hover', modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d'], toImageButtonOptions: { filename: 'oilwell-historical-replay', format: 'png' } });
    }).catch(() => { if (engine.current) setError('Chart could not render. The records remain available in the tables.'); });
  }, [ready, traces, title, yTitle, height, binary]);
  return <div className="plot-wrap" aria-label={title}>{!ready && !error && <div className="chart-loading">Loading chart…</div>}{error && <div role="alert">{error}</div>}<div ref={element} className="plot" style={{ minHeight: height }} /></div>;
}
export function LatestPrediction({ value }: { value?: Prediction }) {
  if (!value) return <Empty>No prediction yet. Inference requires 60 replayed rows and the frozen 10-row stride.</Empty>;
  const p = value.prediction;
  return <div className="prediction-card"><div className="prediction-title"><Status value={p.alert_status} /><span className="mono">Row {value.source_position}</span></div>
    <h3>{p.event_type.replaceAll('_', ' ')}</h3><span className="eyebrow">Selected-class confidence · uncalibrated</span>
    <strong className="confidence">{p.confidence == null ? 'Unavailable' : `${(p.confidence * 100).toFixed(2)}%`}</strong>
    <dl><div><dt>Abnormal score</dt><dd className="mono">{score(p.abnormal_score)}</dd></div><div><dt>Frozen threshold ≥</dt><dd className="mono">{score(p.threshold)}</dd></div><div><dt>Source timestamp</dt><dd>{sourceTime(p.provenance.source_timestamp)}</dd></div><div><dt>Missing sensor cells</dt><dd>{(p.quality.missing_fraction * 100).toFixed(1)}%</dd></div></dl>
    {p.abstention_reason && <p className="notice">{p.abstention_reason.replaceAll('_', ' ')}</p>}
    <p className="fineprint">Model score, not certainty. A binary prediction does not identify the physical event family.</p></div>;
}
