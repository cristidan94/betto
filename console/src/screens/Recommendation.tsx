import { ConsoleShell, type Screen } from '../components/ConsoleShell'
import { Spark, KellyTrace, FeatureWaterfall } from '../components/primitives'
import { useApi } from '../hooks/useApi'
import type { RecommendationDetail } from '../types/recommendation'

export default function Recommendation({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  const { data, loading, error } = useApi<RecommendationDetail>('/recommendations/PM-cs-2891')

  if (loading) {
    return (
      <ConsoleShell active="recs" onNavigate={onNavigate}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <span className="c-muted">Loading...</span>
        </div>
      </ConsoleShell>
    )
  }

  if (error || !data) {
    return (
      <ConsoleShell active="recs" onNavigate={onNavigate}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <span className="c-neg">{error ?? 'Failed to load'}</span>
        </div>
      </ConsoleShell>
    )
  }

  const d = data

  return (
    <ConsoleShell active="recs" onNavigate={onNavigate} crumb={
      <>
        <span>Recs</span>
        <span style={{ color: 'var(--dim)' }}>/</span>
        <span className="num" style={{ color: 'var(--ink-2)' }}>{d.id}</span>
      </>
    }>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* header */}
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="between">
            <div className="col" style={{ gap: 4 }}>
              <span className="eyebrow">{d.strategy} - 3 of 14 today</span>
              <h2 style={{ fontSize: 22, letterSpacing: '-0.01em' }}>
                {d.match}
                <span className="c-muted" style={{ fontWeight: 400 }}> - </span>
                <span style={{ fontWeight: 400 }}>{d.market}</span>
              </h2>
            </div>
            <div className="middle" style={{ gap: 8 }}>
              <span className="chip"><span className="c-muted">starts</span> <span style={{ color: 'var(--ink)' }}>{d.close}</span></span>
              <span className="chip">{d.format} - {d.regime}</span>
              <div className="vr" style={{ height: 18 }} />
              <button className="chip acc" style={{ height: 26, padding: '0 12px', fontSize: 12.5 }}>
                <span className="kbd" style={{ background: 'transparent', borderColor: 'var(--acc-ring)', color: 'var(--acc)' }}>Enter</span>
                Recommend ${d.stake_usd.toFixed(2)}
              </button>
              <button className="chip" style={{ height: 26 }}>Paper only</button>
              <button className="chip" style={{ height: 26 }}>Skip</button>
            </div>
          </div>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            <span className="chip acc">+{(d.edge * 100).toFixed(1)}% edge</span>
            <span className="chip">size {(d.size * 100).toFixed(2)}%</span>
            <span className="chip">conf {d.confidence}</span>
            <span className="chip">1/4 Kelly - cap 2.5%</span>
            <span className="chip"><span className="dot ok" />veto {d.veto.state}</span>
            <span className="chip">corr-cap {(d.derivatives.filter(x => x.state === 'recommend' || x.state === 'add-on').reduce((s, x) => s + x.size, 0) * 100).toFixed(1)} / 5.0%</span>
            <span className="chip"><span className="c-muted">model</span> {d.strategy}</span>
          </div>
        </div>

        {/* body */}
        <div className="grow" style={{ display: 'grid', gridTemplateColumns: '1.5fr 1.1fr 1fr', gap: 0, minHeight: 0 }}>
          {/* col 1: chart + derivatives */}
          <div style={{ borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)', flex: '1.4 1 0', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div className="between" style={{ marginBottom: 10 }}>
                <div className="col" style={{ gap: 2 }}>
                  <span className="eyebrow">model vs market - price</span>
                  <span className="num" style={{ fontSize: 11, color: 'var(--muted)' }}>
                    <span className="c-acc">- - model</span> &nbsp;-&nbsp; <span style={{ color: 'var(--ink-2)' }}>-- market</span>
                  </span>
                </div>
                <div className="middle" style={{ gap: 8 }}>
                  <div className="seg">
                    <button>1h</button>
                    <button>6h</button>
                    <button className="on">24h</button>
                    <button>7d</button>
                    <button>30d</button>
                  </div>
                  <span className="chip ghost c-muted" style={{ fontSize: 11 }}>liquidity $42k</span>
                </div>
              </div>
              <div className="grow" style={{ minHeight: 120, position: 'relative' }}>
                <Spark w={620} h={260} seed={3} model modelOffset={0.13} grid axis />
                <div style={{ position: 'absolute', right: 12, top: 8, padding: 8, background: 'rgba(18,20,22,0.85)', border: '1px solid var(--border)', borderRadius: 5, display: 'flex', flexDirection: 'column', gap: 2, minWidth: 140 }}>
                  <span className="eyebrow" style={{ marginBottom: 2 }}>last tick</span>
                  <div className="between"><span className="c-muted">model</span><span className="num c-acc">{d.model_prob.toFixed(3)}</span></div>
                  <div className="between"><span className="c-muted">market</span><span className="num">{d.market_prob.toFixed(3)}</span></div>
                  <div className="between"><span className="c-muted">decimal</span><span className="num">{(1 / d.market_prob).toFixed(3)}</span></div>
                  <div className="between"><span className="c-muted">edge</span><span className="num c-pos">+{(d.edge * 100).toFixed(1)}%</span></div>
                </div>
              </div>
            </div>

            <div style={{ padding: 16, flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div className="between" style={{ marginBottom: 8 }}>
                <div className="col" style={{ gap: 2 }}>
                  <span className="eyebrow">derivative scanner - same match</span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>internal coherence ok - no triangular arbitrage</span>
                </div>
                <span className="chip ghost c-muted">{d.derivatives.length} markets</span>
              </div>
              <div className="grow" style={{ overflow: 'auto' }}>
                <table className="tbl" style={{ tableLayout: 'fixed' }}>
                  <colgroup>
                    <col />
                    <col style={{ width: 64 }} />
                    <col style={{ width: 64 }} />
                    <col style={{ width: 70 }} />
                    <col style={{ width: 64 }} />
                    <col style={{ width: 100 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Market</th>
                      <th className="num">Model</th>
                      <th className="num">Mkt</th>
                      <th className="num">Edge</th>
                      <th className="num">Size</th>
                      <th>State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.derivatives.map((deriv, i) => (
                      <tr key={i} className={`tbl-row ${deriv.state === 'recommend' ? 'sel' : ''}`} style={{ height: 28 }}>
                        <td>{deriv.market}</td>
                        <td className="num">{deriv.model_prob.toFixed(3)}</td>
                        <td className="num">{deriv.market_prob.toFixed(3)}</td>
                        <td className="num" style={{ color: deriv.edge >= 0 ? 'var(--pos)' : 'var(--neg)', fontWeight: 600 }}>
                          {(deriv.edge >= 0 ? '+' : '') + (deriv.edge * 100).toFixed(1)}%
                        </td>
                        <td className="num">{deriv.size === 0 ? <span className="c-dim">-</span> : (deriv.size * 100).toFixed(2) + '%'}</td>
                        <td>
                          <span className={`badge ${deriv.state === 'recommend' ? 'c-acc' : ''}`} style={{
                            background: deriv.state === 'recommend' ? 'var(--acc-bg)' : deriv.state === 'opposite' ? 'var(--neg-bg)' : 'var(--surf-3)',
                            color: deriv.state === 'recommend' ? 'var(--acc)' : deriv.state === 'opposite' ? 'var(--neg)' : 'var(--muted)',
                          }}>{deriv.state}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* col 2: sizing + veto */}
          <div style={{ borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)' }}>
              <div className="between" style={{ marginBottom: 12 }}>
                <span className="eyebrow">sizing trace</span>
                <span className="chip acc"><span className="num">${d.stake_usd.toFixed(2)}</span></span>
              </div>
              <KellyTrace
                rows={d.sizing_trace.map(s => ({ label: s.label, value: s.value, applied: s.applied }))}
                max={0.10}
              />
              <hr className="hr" style={{ margin: '14px 0' }} />
              <table style={{ width: '100%', fontSize: 12 }}>
                <tbody>
                  <tr>
                    <td className="c-muted" style={{ padding: '3px 0' }}>model p</td>
                    <td className="num" style={{ textAlign: 'right', padding: '3px 0' }}>{d.model_prob.toFixed(4)}</td>
                    <td className="c-muted" style={{ paddingLeft: 24 }}>b (price)</td>
                    <td className="num" style={{ textAlign: 'right' }}>{(1 / d.market_prob - 1 + 1).toFixed(3)}</td>
                  </tr>
                  <tr>
                    <td className="c-muted" style={{ padding: '3px 0' }}>market p</td>
                    <td className="num" style={{ textAlign: 'right', padding: '3px 0' }}>{d.market_prob.toFixed(4)}</td>
                    <td className="c-muted" style={{ paddingLeft: 24 }}>stake</td>
                    <td className="num" style={{ textAlign: 'right' }}>${d.stake_usd.toFixed(2)}</td>
                  </tr>
                  <tr>
                    <td className="c-muted" style={{ padding: '3px 0' }}>edge</td>
                    <td className="num c-pos" style={{ textAlign: 'right', padding: '3px 0' }}>+{d.edge.toFixed(4)}</td>
                    <td className="c-muted" style={{ paddingLeft: 24 }}>to win</td>
                    <td className="num" style={{ textAlign: 'right' }}>${(d.stake_usd * (1 / d.market_prob - 1)).toFixed(2)}</td>
                  </tr>
                  <tr>
                    <td className="c-muted" style={{ padding: '3px 0' }}>f* Kelly</td>
                    <td className="num" style={{ textAlign: 'right', padding: '3px 0' }}>{d.sizing_trace[0]?.value.toFixed(4)}</td>
                    <td className="c-muted" style={{ paddingLeft: 24 }}>EV (model)</td>
                    <td className="num c-pos" style={{ textAlign: 'right' }}>+${(d.stake_usd * d.edge / d.market_prob).toFixed(2)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="grow" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0, overflow: 'auto' }}>
              <div className="col" style={{ gap: 8 }}>
                <span className="eyebrow">veto state</span>
                <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                  <span className="chip pos"><span className="dot ok" />{d.veto.state} - {d.veto.vetoed} / {d.veto.total} vetoed</span>
                  <span className="chip">{d.format}</span>
                </div>
                <div className="row" style={{ gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                  {d.veto.maps.map((m) => (
                    <span key={m} className="badge" style={{ background: 'var(--surf-2)', color: 'var(--ink-2)' }}>{m}</span>
                  ))}
                </div>
                <span className="c-muted" style={{ fontSize: 11, marginTop: 2 }}>veto-conditional repricing armed (v2 - shadow)</span>
              </div>
              <hr className="hr" />
              <div className="col" style={{ gap: 8 }}>
                <span className="eyebrow">match context</span>
                <table style={{ width: '100%', fontSize: 12 }}>
                  <tbody>
                    <tr><td className="c-muted" style={{ padding: '2px 0' }}>regime</td><td className="num" style={{ textAlign: 'right' }}>{d.regime}</td></tr>
                    <tr><td className="c-muted" style={{ padding: '2px 0' }}>timezone gap</td><td className="num" style={{ textAlign: 'right' }}>{d.context.timezone_gap}</td></tr>
                    <tr><td className="c-muted" style={{ padding: '2px 0' }}>{d.match.split(' vs ')[0]} roster</td><td className="num" style={{ textAlign: 'right' }}>{d.context.roster_a}</td></tr>
                    <tr><td className="c-muted" style={{ padding: '2px 0' }}>{d.match.split(' vs ')[1]} roster</td><td className="num" style={{ textAlign: 'right' }}>{d.context.roster_b}</td></tr>
                    <tr><td className="c-muted" style={{ padding: '2px 0' }}>stand-ins</td><td className="num" style={{ textAlign: 'right' }}>{d.context.stand_ins}</td></tr>
                    <tr><td className="c-muted" style={{ padding: '2px 0' }}>news - 24h</td><td className="num" style={{ textAlign: 'right' }}>{d.context.news_24h}</td></tr>
                    <tr><td className="c-muted" style={{ padding: '2px 0' }}>schedule</td><td className="num" style={{ textAlign: 'right' }}>{d.context.schedule}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* col 3: features */}
          <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)' }}>
              <div className="between" style={{ marginBottom: 10 }}>
                <div className="col" style={{ gap: 2 }}>
                  <span className="eyebrow">feature contributions</span>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>log-odds added to base rate</span>
                </div>
                <span className="chip ghost"><span className="num c-muted">{d.features.length} features</span></span>
              </div>
              <FeatureWaterfall rows={d.features} max={0.04} />
              <hr className="hr" style={{ margin: '14px 0' }} />
              <div className="col" style={{ gap: 6, fontSize: 12 }}>
                <div className="between"><span className="c-muted">base rate</span><span className="num">0.500</span></div>
                <div className="between"><span className="c-muted">+ contributions</span><span className="num c-pos">+{d.features.reduce((s, f) => s + f.value, 0).toFixed(3)}</span></div>
                <div className="between" style={{ paddingTop: 4, borderTop: '1px solid var(--rule)' }}>
                  <span style={{ color: 'var(--ink)' }}>model p</span>
                  <span className="num c-acc" style={{ fontSize: 14 }}>{d.model_prob.toFixed(3)}</span>
                </div>
              </div>
            </div>

            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)' }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>strategy health - {d.strategy}</div>
              <table style={{ width: '100%', fontSize: 12 }}>
                <tbody>
                  <tr><td className="c-muted" style={{ padding: '3px 0' }}>30d CLV</td><td className="num c-pos" style={{ textAlign: 'right' }}>+{(d.strategy_health.clv_30d * 100).toFixed(1)}%</td></tr>
                  <tr><td className="c-muted" style={{ padding: '3px 0' }}>30d paper ROI</td><td className="num c-pos" style={{ textAlign: 'right' }}>+{(d.strategy_health.paper_roi_30d * 100).toFixed(1)}%</td></tr>
                  <tr><td className="c-muted" style={{ padding: '3px 0' }}>calibration ECE</td><td className="num" style={{ textAlign: 'right' }}>{d.strategy_health.calibration_ece.toFixed(3)}</td></tr>
                  <tr><td className="c-muted" style={{ padding: '3px 0' }}>drift</td><td style={{ textAlign: 'right' }}><span className="chip warn" style={{ height: 18, fontSize: 10.5 }}>+{d.strategy_health.drift_ece.toFixed(2)} ECE</span></td></tr>
                  <tr><td className="c-muted" style={{ padding: '3px 0' }}>days since refit</td><td className="num" style={{ textAlign: 'right' }}>{d.strategy_health.days_since_refit}</td></tr>
                </tbody>
              </table>
            </div>

            <div className="grow" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div className="eyebrow">lineage</div>
              <div className="col" style={{ gap: 4, fontSize: 11.5, color: 'var(--ink-2)' }}>
                <div className="between"><span className="c-muted">model</span><span className="num">{d.lineage.model} - {d.lineage.model_hash}</span></div>
                <div className="between"><span className="c-muted">features</span><span className="num">snapshot {d.lineage.feature_snapshot}</span></div>
                <div className="between"><span className="c-muted">market snap</span><span className="num">{d.lineage.market_snapshot}  +2s</span></div>
                <div className="between"><span className="c-muted">backtest</span><span className="num">run #{d.lineage.backtest_run}</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ConsoleShell>
  )
}
