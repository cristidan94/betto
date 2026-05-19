import { ConsoleShell, type Screen } from '../components/ConsoleShell'
import { Equity, Calibration, Histogram, Status } from '../components/primitives'

export default function Backtests({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  const edgeRows = [
    { min: '≥ 1%', n: 9210, roi: '+0.4%', clv: '+0.6%', dd: '-18%', star: false, neg: true },
    { min: '≥ 2%', n: 5140, roi: '+1.7%', clv: '+1.1%', dd: '-13%', star: false, neg: true },
    { min: '≥ 3%', n: 2612, roi: '+3.6%', clv: '+1.8%', dd: '-9.8%', star: true, neg: false },
    { min: '≥ 4%', n: 1318, roi: '+4.1%', clv: '+2.2%', dd: '-11%', star: false, neg: false },
    { min: '≥ 5%', n: 682, roi: '+3.9%', clv: '+2.4%', dd: '-14%', star: false, neg: false },
  ]

  const slices = [
    { dim: 'LAN', roi: '+4.2%', clv: '+2.1%', n: 1840, kind: 'pos' },
    { dim: 'online', roi: '+3.1%', clv: '+1.5%', n: 772, kind: 'pos' },
    { dim: 'Tier 1', roi: '+4.6%', clv: '+2.3%', n: 1320, kind: 'pos' },
    { dim: 'Tier 2', roi: '+2.1%', clv: '+1.0%', n: 1292, kind: null },
    { dim: 'Favorite', roi: '+2.8%', clv: '+1.3%', n: 1518, kind: null },
    { dim: 'Dog', roi: '+4.7%', clv: '+2.4%', n: 1094, kind: 'pos' },
    { dim: 'Bo3', roi: '+3.8%', clv: '+1.9%', n: 1810, kind: 'pos' },
    { dim: 'Bo1', roi: '+1.4%', clv: '+0.5%', n: 410, kind: null },
  ]

  return (
    <ConsoleShell active="backtest" onNavigate={onNavigate} crumb={
      <>
        <span>Backtests</span>
        <span style={{ color: 'var(--dim)' }}>›</span>
        <span className="num" style={{ color: 'var(--ink-2)' }}>run #214</span>
      </>
    }>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)' }}>
          <div className="between">
            <div className="col" style={{ gap: 4 }}>
              <span className="eyebrow">walk-forward · jan 2024 → may 2026 · ¼ kelly · cap 2.5%</span>
              <h2 style={{ fontSize: 22, letterSpacing: '-0.01em' }}>
                map-winner
                <span className="c-muted" style={{ fontWeight: 400 }}> · </span>
                <span className="num" style={{ fontSize: 16, color: 'var(--ink-2)', fontWeight: 500 }}>v1.4 → v1.3</span>
              </h2>
            </div>
            <div className="middle" style={{ gap: 8 }}>
              <span className="chip"><span className="num c-muted">n =</span> <span className="num" style={{ color: 'var(--ink)' }}>4,128 maps</span></span>
              <span className="chip">window 90d / step 7d</span>
              <span className="chip pos"><span className="dot ok" />leakage 8 / 8</span>
              <div className="vr" style={{ height: 18 }} />
              <button className="chip" style={{ height: 26 }}>Export</button>
              <button className="chip acc" style={{ height: 26 }}>
                <span className="kbd" style={{ background: 'transparent', borderColor: 'var(--acc-ring)', color: 'var(--acc)' }}>↵</span>
                Promote to v1.4
              </button>
            </div>
          </div>
        </div>

        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--rule)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {[
              { l: 'CAGR', v: '+34%', hint: 'paper ¼ kelly', k: 'pos' },
              { l: 'Sharpe', v: '1.41', hint: '4.5y · daily', k: null },
              { l: 'max DD', v: '-9.8%', hint: 'dec 2024', k: 'neg' },
              { l: 'avg CLV', v: '+1.6%', hint: 'vs close', k: 'pos' },
              { l: 'turnover', v: '12.4', hint: 'bets / week', k: null },
              { l: 'calibration ECE', v: '0.024', hint: 'overall', k: null },
            ].map((k, i) => (
              <div key={i} style={{ background: 'var(--surf)', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="eyebrow">{k.l}</span>
                <span className="num" style={{ fontSize: 19, fontWeight: 600, color: k.k === 'pos' ? 'var(--pos)' : k.k === 'neg' ? 'var(--neg)' : 'var(--ink)' }}>{k.v}</span>
                <span className="c-muted" style={{ fontSize: 10.5 }}>{k.hint}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="grow" style={{ display: 'grid', gridTemplateColumns: '1.45fr 1fr 1fr', minHeight: 0 }}>
          <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border)', minHeight: 0 }}>
            <div style={{ padding: 16, flex: '1.4 1 0', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div className="between" style={{ marginBottom: 8 }}>
                <span className="eyebrow">paper equity · simulated</span>
                <div className="seg">
                  <button>linear</button>
                  <button className="on">log</button>
                </div>
              </div>
              <div className="grow" style={{ minHeight: 0 }}>
                <Equity w={580} h={280} seed={9} points={140} drawdown />
              </div>
              <div className="row" style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--rule)', gap: 18 }}>
                <div className="col"><span className="eyebrow">start</span><span className="num">$10,000</span></div>
                <div className="col"><span className="eyebrow">end</span><span className="num c-pos">$28,420</span></div>
                <div className="col"><span className="eyebrow">profit</span><span className="num c-pos">+$18,420</span></div>
                <div className="col"><span className="eyebrow">months</span><span className="num">28</span></div>
              </div>
            </div>
            <div style={{ padding: 16, borderTop: '1px solid var(--rule)' }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>leakage / definition-of-done checks</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 14, rowGap: 6, fontSize: 12 }}>
                <Status kind="ok">point-in-time feature snapshot</Status>
                <Status kind="ok">close-after-prediction</Status>
                <Status kind="ok">no future-leak in Elo</Status>
                <Status kind="ok">veto resolved before t₀</Status>
                <Status kind="ok">unit + integration tests</Status>
                <Status kind="ok">idempotent runs</Status>
                <Status kind="ok">structured run metadata</Status>
                <Status kind="ok">CLI entrypoint · cli.py</Status>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border)', minHeight: 0 }}>
            <div style={{ padding: 16, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div className="between" style={{ marginBottom: 6 }}>
                <span className="eyebrow">reliability · calibration</span>
                <span className="chip ghost"><span className="c-muted">ECE</span> <span className="num" style={{ color: 'var(--ink)' }}>0.024</span></span>
              </div>
              <div className="grow" style={{ minHeight: 0, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '12px 8px' }}>
                <div style={{ width: '100%', maxWidth: 320, aspectRatio: '1 / 1' }}>
                  <Calibration w={320} h={320} />
                </div>
                <span style={{ position: 'absolute', left: 14, bottom: 12, fontSize: 10.5, color: 'var(--muted)' }}>predicted →</span>
                <span style={{ position: 'absolute', top: 8, left: 14, fontSize: 10.5, color: 'var(--muted)', writingMode: 'vertical-rl' }}>↑ realized</span>
              </div>
              <div className="c-muted" style={{ fontSize: 11.5, marginTop: 4 }}>Slight under-confidence at p &gt; 0.65 — monitor on next refit.</div>
            </div>
            <div style={{ padding: 16, borderTop: '1px solid var(--rule)' }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>CLV distribution · settled bets</div>
              <div style={{ height: 72 }}>
                <Histogram w={320} h={72} seed={11} bins={26} />
              </div>
              <div className="row" style={{ marginTop: 6, gap: 16, fontSize: 11.5 }}>
                <div><span className="c-muted">mean </span><span className="num c-pos">+1.6%</span></div>
                <div><span className="c-muted">median </span><span className="num">+1.4%</span></div>
                <div><span className="c-muted">% &gt; 0 </span><span className="num">61%</span></div>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)' }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>edge filter response</div>
              <table className="tbl">
                <colgroup>
                  <col style={{ width: 64 }} />
                  <col style={{ width: 72 }} />
                  <col />
                  <col />
                  <col style={{ width: 60 }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>min edge</th>
                    <th className="num">n</th>
                    <th className="num">ROI</th>
                    <th className="num">CLV</th>
                    <th className="num">DD</th>
                  </tr>
                </thead>
                <tbody>
                  {edgeRows.map((r, i) => (
                    <tr key={i} className={`tbl-row ${r.star ? 'sel' : ''}`} style={{ height: 26 }}>
                      <td>{r.min}{r.star && <span className="c-acc" style={{ marginLeft: 4 }}>★</span>}</td>
                      <td className="num">{r.n.toLocaleString()}</td>
                      <td className="num" style={{ color: 'var(--pos)' }}>{r.roi}</td>
                      <td className="num" style={{ color: 'var(--pos)' }}>{r.clv}</td>
                      <td className="num" style={{ color: r.neg ? 'var(--neg)' : 'var(--ink-2)' }}>{r.dd}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="c-muted" style={{ fontSize: 11.5, marginTop: 6 }}>★ chosen filter — best CLV/DD trade.</div>
            </div>
            <div className="grow" style={{ padding: 16, minHeight: 0, overflow: 'auto' }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>sliced ROI · CLV</div>
              <table className="tbl">
                <colgroup>
                  <col />
                  <col style={{ width: 68 }} />
                  <col style={{ width: 68 }} />
                  <col style={{ width: 56 }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>slice</th>
                    <th className="num">ROI</th>
                    <th className="num">CLV</th>
                    <th className="num">n</th>
                  </tr>
                </thead>
                <tbody>
                  {slices.map((s, i) => (
                    <tr key={i} className="tbl-row" style={{ height: 26 }}>
                      <td>{s.dim}</td>
                      <td className="num" style={{ color: s.kind === 'pos' ? 'var(--pos)' : 'var(--ink-2)', fontWeight: s.kind === 'pos' ? 600 : 500 }}>{s.roi}</td>
                      <td className="num" style={{ color: s.kind === 'pos' ? 'var(--pos)' : 'var(--ink-2)' }}>{s.clv}</td>
                      <td className="num c-muted">{s.n.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </ConsoleShell>
  )
}
