import { ConsoleShell, type Screen } from '../components/ConsoleShell'
import { Spark, Status } from '../components/primitives'
import { useApi } from '../hooks/useApi'
import type { FeatureFreshness, IngestionResponse, IngestionSource } from '../types/ingestion'

function IngestionState({ children, onNavigate, tone = 'muted' }: { children: string; onNavigate: (s: Screen) => void; tone?: 'muted' | 'neg' }) {
  return (
    <ConsoleShell active="ingest" onNavigate={onNavigate}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <span className={tone === 'neg' ? 'c-neg' : 'c-muted'}>{children}</span>
      </div>
    </ConsoleShell>
  )
}

function sourceChipClass(kind: string) {
  if (kind === 'warn') return 'chip warn'
  if (kind === 'idle') return 'chip ghost'
  return 'chip pos'
}

export default function Ingestion({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  const { data, loading, error } = useApi<IngestionResponse>('/ingestion')

  if (loading) return <IngestionState onNavigate={onNavigate}>Loading...</IngestionState>
  if (error || !data) return <IngestionState onNavigate={onNavigate} tone="neg">{error ?? 'Failed to load'}</IngestionState>

  const sources = data.sources
  const features = data.features
  const warning = sources.find((source) => source.kind === 'warn') ?? features.find((feature) => feature.kind === 'warn')
  const freshnessOk = sources.every((source) => source.kind === 'ok') && features.every((feature) => feature.kind === 'ok')

  return (
    <ConsoleShell active="ingest" onNavigate={onNavigate}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)' }}>
          <div className="between">
            <div className="col" style={{ gap: 4 }}>
              <span className="eyebrow">data plane - sources - jobs - freshness</span>
              <h2 style={{ fontSize: 22 }}>
                Ingestion
                <span className="c-muted" style={{ fontWeight: 400, fontSize: 14, marginLeft: 10 }}>live contract</span>
              </h2>
            </div>
            <div className="middle" style={{ gap: 8 }}>
              <span className={data.schemas_ok ? 'chip pos' : 'chip neg'}><span className={data.schemas_ok ? 'dot ok' : 'dot bad'} />schemas {data.schemas_ok ? 'ok' : 'fail'}</span>
              <span className={data.leakage_tests_ok ? 'chip pos' : 'chip neg'}><span className={data.leakage_tests_ok ? 'dot ok' : 'dot bad'} />leakage {data.leakage_tests_ok ? 'ok' : 'fail'}</span>
              <span className={warning ? 'chip warn' : 'chip pos'}><span className={warning ? 'dot warn' : 'dot ok'} />{warning ? `${warning.name} ${warning.fresh}` : 'freshness ok'}</span>
              <div className="vr" style={{ height: 18 }} />
              <button className="chip" style={{ height: 26 }}>Replay snapshots</button>
            </div>
          </div>
        </div>

        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--rule)' }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>sources - {sources.length}</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
            {sources.map((source: IngestionSource) => (
              <div key={source.name} className="card" style={{
                padding: 14,
                borderColor: source.kind === 'warn' ? 'rgba(216,165,65,0.4)' : 'var(--border)',
                background: source.kind === 'warn' ? 'linear-gradient(180deg, rgba(216,165,65,0.04), var(--surf))' : 'var(--surf)',
              }}>
                <div className="between" style={{ marginBottom: 8 }}>
                  <div className="middle" style={{ gap: 8, minWidth: 0 }}>
                    <span className={`dot ${source.kind}`} />
                    <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{source.name}</span>
                  </div>
                  <span className={sourceChipClass(source.kind)} style={{ height: 20, fontSize: 11 }}>
                    {source.on ? 'on' : 'off'}
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12, rowGap: 6 }}>
                  <div className="col"><span className="eyebrow">freshness</span><span className="num" style={{ fontSize: 18, color: source.kind === 'warn' ? 'var(--warn)' : 'var(--ink)' }}>{source.fresh}</span></div>
                  <div className="col"><span className="eyebrow">target</span><span className="num" style={{ fontSize: 13, color: 'var(--muted)' }}>{source.target}</span></div>
                  <div className="col"><span className="eyebrow">cadence</span><span className="num" style={{ fontSize: 13 }}>{source.cadence}</span></div>
                  <div className="col"><span className="eyebrow">rows</span><span className="num" style={{ fontSize: 13 }}>{source.rows.toLocaleString()}</span></div>
                </div>
                <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--rule)', display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11.5 }}>
                  <span className="c-muted">last error</span>
                  <span className={source.kind === 'warn' ? 'c-neg' : 'c-muted'} style={{ fontFamily: 'var(--mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{source.last_error}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grow" style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', minHeight: 0 }}>
          <div style={{ padding: 16, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div className="between" style={{ marginBottom: 8 }}>
              <div className="col" style={{ gap: 2 }}>
                <span className="eyebrow">market snapshot lag</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  latest <span className="num" style={{ color: 'var(--ink)' }}>{data.snapshot_lag}</span> - stored <span className="num" style={{ color: 'var(--ink)' }}>{data.snapshot_count.toLocaleString()}</span>
                </span>
              </div>
              <div className="seg">
                <button>1h</button>
                <button className="on">6h</button>
                <button>24h</button>
                <button>7d</button>
              </div>
            </div>
            <div className="grow" style={{ minHeight: 120, position: 'relative' }}>
              <Spark w={620} h={220} seed={31} grid axis />
              <div style={{ position: 'absolute', left: 0, right: 0, top: '60%', borderTop: '1px dashed var(--warn)', opacity: 0.5, pointerEvents: 'none' }} />
              <div style={{ position: 'absolute', right: 8, top: 'calc(60% - 18px)', fontSize: 10, color: 'var(--warn)', fontFamily: 'var(--mono)' }}>SLA</div>
            </div>
            <div className="row" style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--rule)', gap: 18 }}>
              <div className="col"><span className="eyebrow">snapshots</span><span className="num" style={{ fontSize: 14 }}>{data.snapshot_count.toLocaleString()}</span></div>
              <div className="col"><span className="eyebrow">lag</span><span className="num" style={{ fontSize: 14 }}>{data.snapshot_lag}</span></div>
              <div className="col"><span className="eyebrow">sources</span><span className="num" style={{ fontSize: 14 }}>{sources.length}</span></div>
              <div className="col"><span className="eyebrow">features</span><span className="num" style={{ fontSize: 14 }}>{features.length}</span></div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)' }}>
              <div className="between" style={{ marginBottom: 8 }}>
                <span className="eyebrow">feature freshness - point-in-time</span>
                <span className={freshnessOk ? 'chip pos' : 'chip warn'}><span className={freshnessOk ? 'dot ok' : 'dot warn'} />{freshnessOk ? 'all fresh' : 'watch'}</span>
              </div>
              <table className="tbl">
                <colgroup>
                  <col />
                  <col style={{ width: 80 }} />
                  <col style={{ width: 72 }} />
                  <col style={{ width: 36 }} />
                </colgroup>
                <tbody>
                  {features.map((feature: FeatureFreshness) => (
                    <tr key={feature.name} className="tbl-row" style={{ height: 26 }}>
                      <td style={{ fontSize: 12 }}>{feature.name}</td>
                      <td className="num" style={{ color: feature.kind === 'warn' ? 'var(--warn)' : 'var(--ink-2)' }}>{feature.fresh}</td>
                      <td className="num c-muted">{feature.rows.toLocaleString()}</td>
                      <td><span className={`dot ${feature.kind}`} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grow" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="eyebrow">validation</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12, rowGap: 6, fontSize: 12 }}>
                <Status kind={data.schemas_ok ? 'ok' : 'bad'}>schema validation</Status>
                <Status kind={data.leakage_tests_ok ? 'ok' : 'bad'}>leakage tests</Status>
                <Status kind="ok">snapshot lineage</Status>
                <Status kind="ok">idempotency</Status>
              </div>
              <span className="c-muted" style={{ fontSize: 11, marginTop: 4 }}>
                The API surfaces raw source freshness, feature recency, and market snapshot lag from fixtures or Postgres.
              </span>
            </div>
          </div>
        </div>
      </div>
    </ConsoleShell>
  )
}
