import { ConsoleShell, type ScreenProps } from '../components/ConsoleShell'
import { Equity } from '../components/primitives'
import { useApi } from '../hooks/useApi'
import type { CapitalBucket, KillSwitch, RiskCap, RiskKpi, RiskResponse } from '../types/risk'

function RiskState({ children, onNavigate, mode, onModeChange, tone = 'muted' }: ScreenProps & { children: string; tone?: 'muted' | 'neg' }) {
  return (
    <ConsoleShell active="risk" onNavigate={onNavigate} mode={mode} onModeChange={onModeChange}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <span className={tone === 'neg' ? 'c-neg' : 'c-muted'}>{children}</span>
      </div>
    </ConsoleShell>
  )
}

function toneColor(kind: string | null) {
  if (kind === 'pos') return 'var(--pos)'
  if (kind === 'neg') return 'var(--neg)'
  if (kind === 'warn') return 'var(--warn)'
  return 'var(--ink)'
}

export default function Risk({ onNavigate, mode, onModeChange }: ScreenProps) {
  const { data, loading, error } = useApi<RiskResponse>('/risk')
  const shellProps = { mode, onModeChange }

  if (loading) return <RiskState onNavigate={onNavigate} {...shellProps}>Loading...</RiskState>
  if (error || !data) return <RiskState onNavigate={onNavigate} {...shellProps} tone="neg">{error ?? 'Failed to load'}</RiskState>

  const allocated = data.buckets.filter((bucket) => bucket.kind !== 'flat').reduce((sum, bucket) => sum + bucket.used, 0)
  const reserve = data.buckets.find((bucket) => bucket.kind === 'flat')?.used ?? Math.max(0, 100 - allocated)

  if (data.kpis.length === 0 && data.buckets.length === 0 && data.caps.length === 0 && data.kill_switches.length === 0) {
    return (
      <ConsoleShell active="risk" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'grid', placeItems: 'center', height: '100%', padding: 24 }}>
          <div className="card" style={{ width: 'min(520px, 100%)', padding: 18, textAlign: 'center' }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>risk</div>
            <h3 style={{ fontSize: 18, marginBottom: 6 }}>No risk data loaded</h3>
            <p className="c-muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
              Generate recommendations, bets, or risk summaries to populate this view.
            </p>
          </div>
        </div>
      </ConsoleShell>
    )
  }

  return (
    <ConsoleShell active="risk" onNavigate={onNavigate} {...shellProps}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)' }}>
          <div className="between">
            <div className="col" style={{ gap: 4 }}>
              <span className="eyebrow">capital - caps - kill switches</span>
              <h2 style={{ fontSize: 22 }}>
                Risk
                <span className="c-muted" style={{ fontWeight: 400, fontSize: 14, marginLeft: 10 }}>cs v1 - paper</span>
              </h2>
            </div>
            <div className="middle" style={{ gap: 8 }}>
              <button className="chip" style={{ height: 26 }}>Edit caps</button>
              <button className="chip warn" style={{ height: 26 }}>Freeze sizing</button>
              <button className="chip neg" style={{ height: 26 }}><span className="dot bad" />Global kill</button>
            </div>
          </div>
        </div>

        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--rule)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(data.kpis.length, 1)}, minmax(130px, 1fr))`, gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {data.kpis.map((kpi: RiskKpi) => (
              <div key={kpi.label} style={{ background: 'var(--surf)', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="eyebrow">{kpi.label}</span>
                <span className="num" style={{ fontSize: 22, fontWeight: 600, color: toneColor(kpi.kind) }}>{kpi.value}</span>
                <span className="c-muted" style={{ fontSize: 11 }}>{kpi.hint}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="grow" style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', minHeight: 0 }}>
          <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border)', minHeight: 0 }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)' }}>
              <div className="between" style={{ marginBottom: 10 }}>
                <span className="eyebrow">capital buckets - % of bankroll</span>
                <span className="c-muted" style={{ fontSize: 11.5 }}>
                  allocated <span className="num" style={{ color: 'var(--ink)' }}>{allocated.toFixed(1)}%</span> - reserve <span className="num" style={{ color: 'var(--ink)' }}>{reserve.toFixed(1)}%</span>
                </span>
              </div>
              <div className="col" style={{ gap: 9 }}>
                {data.buckets.map((bucket: CapitalBucket) => (
                  <div key={bucket.name} className="col" style={{ gap: 4 }}>
                    <div className="between">
                      <span className="middle" style={{ gap: 8 }}>
                        <span style={{ fontSize: 12.5, color: 'var(--ink)' }}>{bucket.name}</span>
                        <span className={`chip ${bucket.kind === 'warn' ? 'warn' : bucket.kind === 'flat' || bucket.kind === 'muted' ? '' : 'pos'}`} style={{ height: 18, fontSize: 10.5 }}>
                          {bucket.state}
                        </span>
                      </span>
                      <span className="num" style={{ fontSize: 11.5 }}>
                        <span style={{ color: bucket.kind === 'flat' ? 'var(--muted)' : 'var(--ink)' }}>{bucket.used.toFixed(1)}%</span>
                        {bucket.cap > 0 && <span className="c-muted"> / {bucket.cap.toFixed(bucket.cap < 10 ? 1 : 0)}%</span>}
                      </span>
                    </div>
                    <div className="bar">
                      <i className={bucket.kind === 'acc' ? 'acc' : bucket.kind === 'pos' ? 'pos' : bucket.kind === 'warn' ? 'warn' : ''} style={{
                        width: `${bucket.cap ? Math.min(100, (bucket.used / Math.max(bucket.cap, 1)) * 100) : 100}%`,
                        opacity: bucket.kind === 'muted' ? 0.3 : 1,
                      }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grow" style={{ padding: 16, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
              <div className="between" style={{ marginBottom: 8 }}>
                <span className="eyebrow">drawdown - 90d</span>
                <span className="num" style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                  current <span className="num">paper</span> - tol <span className="num c-muted">-10%</span>
                </span>
              </div>
              <div className="grow" style={{ minHeight: 0, position: 'relative' }}>
                <Equity w={620} h={220} seed={17} points={90} drawdown />
                {[
                  { y: '70%', label: 'warn band - -5%', color: 'var(--warn)' },
                  { y: '82%', label: 'auto-disarm - -7%', color: 'var(--neg)' },
                  { y: '94%', label: 'hard kill - -10%', color: 'var(--neg)' },
                ].map((threshold) => (
                  <div key={threshold.label} style={{ position: 'absolute', left: 0, right: 0, top: threshold.y, pointerEvents: 'none', borderTop: `1px dashed ${threshold.color}`, opacity: 0.7 }}>
                    <span style={{ position: 'absolute', right: 8, top: -16, fontSize: 10, color: threshold.color, fontFamily: 'var(--mono)', background: 'rgba(12,13,14,0.85)', padding: '0 4px' }}>{threshold.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)' }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>caps</div>
              <div className="col" style={{ gap: 8 }}>
                {data.caps.map((cap: RiskCap) => (
                  <div key={cap.label} className="between" style={{ paddingBottom: 8, borderBottom: '1px solid var(--rule)', gap: 12 }}>
                    <div className="col" style={{ gap: 2, minWidth: 0 }}>
                      <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>{cap.label}</span>
                      <span className="c-muted" style={{ fontSize: 11 }}>{cap.hint}</span>
                    </div>
                    <span className="num" style={{ fontSize: 15, color: cap.value === 'off' ? 'var(--muted)' : 'var(--ink)' }}>{cap.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="grow" style={{ padding: 16, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
              <div className="between" style={{ marginBottom: 10 }}>
                <span className="eyebrow">kill switches</span>
                <span className="chip pos"><span className="dot ok" />global armed</span>
              </div>
              <div className="grow" style={{ overflow: 'auto' }}>
                <table className="tbl">
                  <colgroup>
                    <col />
                    <col style={{ width: 100 }} />
                    <col style={{ width: 36 }} />
                  </colgroup>
                  <tbody>
                    {data.kill_switches.map((kill: KillSwitch) => (
                      <tr key={kill.name} className="tbl-row" style={{ height: 36 }}>
                        <td>
                          <div className="col" style={{ gap: 2 }}>
                            <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>{kill.name}</span>
                            <span className="c-muted" style={{ fontSize: 10.5 }}>{kill.trigger}</span>
                          </div>
                        </td>
                        <td className="num">
                          <span className="badge" style={{
                            background: kill.kind === 'ok' ? 'var(--pos-bg)' : kill.kind === 'warn' ? 'var(--warn-bg)' : 'var(--surf-3)',
                            color: kill.kind === 'ok' ? 'var(--pos)' : kill.kind === 'warn' ? 'var(--warn)' : 'var(--muted)',
                          }}>{kill.state}</span>
                        </td>
                        <td><span className={`dot ${kill.kind === 'muted' ? 'idle' : kill.kind}`} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ConsoleShell>
  )
}
