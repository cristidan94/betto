import { ConsoleShell, type Screen } from '../components/ConsoleShell'
import { Equity } from '../components/primitives'
import { useApi } from '../hooks/useApi'
import type { SettledBet, StrategyResponse } from '../types/strategy'

function StrategyState({ children, onNavigate, tone = 'muted' }: { children: string; onNavigate: (s: Screen) => void; tone?: 'muted' | 'neg' }) {
  return (
    <ConsoleShell active="strats" onNavigate={onNavigate}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <span className={tone === 'neg' ? 'c-neg' : 'c-muted'}>{children}</span>
      </div>
    </ConsoleShell>
  )
}

export default function Strategies({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  const { data, loading, error } = useApi<StrategyResponse>('/strategies/map-winner')

  if (loading) return <StrategyState onNavigate={onNavigate}>Loading...</StrategyState>
  if (error || !data) return <StrategyState onNavigate={onNavigate} tone="neg">{error ?? 'Failed to load'}</StrategyState>

  const settled = data.settled
  const accepted = data.kpis.find((k) => k.label.toLowerCase() === 'accepted')?.value ?? '0'
  const roi = data.kpis.find((k) => k.label.toLowerCase().includes('roi'))?.value ?? '0.0%'
  const clv = data.kpis.find((k) => k.label.toLowerCase().includes('clv'))?.value ?? '0.0%'
  const capital = data.kpis.find((k) => k.label.toLowerCase().includes('capital'))?.value ?? '0.0%'

  return (
    <ConsoleShell active="strats" onNavigate={onNavigate} crumb={
      <>
        <span>Strategies</span>
        <span style={{ color: 'var(--dim)' }}>/</span>
        <span className="num" style={{ color: 'var(--ink-2)' }}>{data.strategy_id}</span>
      </>
    }>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)' }}>
          <div className="between">
            <div className="col" style={{ gap: 4 }}>
              <span className="eyebrow">strategy - plugin module</span>
              <h2 style={{ fontSize: 22, letterSpacing: '-0.01em' }}>
                {data.name}
                <span className="c-muted" style={{ fontWeight: 400 }}> - </span>
                <span className="num" style={{ fontSize: 16, color: 'var(--ink-2)', fontWeight: 500 }}>{data.version}</span>
              </h2>
            </div>
            <div className="middle" style={{ gap: 8 }}>
              <span className={data.enabled ? 'chip pos' : 'chip warn'}><span className={data.enabled ? 'dot ok' : 'dot warn'} />flag - {data.enabled ? 'on' : 'off'}</span>
              <span className="chip">{data.mode}</span>
              <span className="chip">30d live</span>
              <div className="vr" style={{ height: 18 }} />
              <button className="chip" style={{ height: 26 }}>Freeze sizing</button>
              <button className="chip warn" style={{ height: 26 }}>Roll back</button>
              <button className="chip neg" style={{ height: 26 }}><span className="dot bad" />Kill</button>
            </div>
          </div>
        </div>

        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--rule)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(data.kpis.length, 1)}, minmax(110px, 1fr))`, gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
            {data.kpis.map((k) => (
              <div key={k.label} style={{ background: 'var(--surf)', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span className="eyebrow">{k.label}</span>
                <span className="num" style={{ fontSize: 19, fontWeight: 600, color: k.kind === 'pos' ? 'var(--pos)' : k.kind === 'warn' ? 'var(--warn)' : k.kind === 'neg' ? 'var(--neg)' : 'var(--ink)' }}>{k.value}</span>
                <span className="c-muted" style={{ fontSize: 10.5 }}>{k.hint}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="grow" style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', minHeight: 0 }}>
          <div style={{ padding: 16, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div className="between" style={{ marginBottom: 8 }}>
              <div className="col" style={{ gap: 2 }}>
                <span className="eyebrow">paper P&L - walk-forward - 1/4 kelly</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>{accepted} accepted - ROI {roi} - CLV {clv}</span>
              </div>
              <div className="middle" style={{ gap: 8 }}>
                <div className="seg">
                  <button>7d</button>
                  <button className="on">30d</button>
                  <button>90d</button>
                  <button>YTD</button>
                </div>
                <span className="chip ghost"><span className="num c-muted">n = {accepted}</span></span>
              </div>
            </div>
            <div className="grow" style={{ minHeight: 0, position: 'relative' }}>
              <Equity w={760} h={300} seed={2} points={90} drawdown />
              <div style={{ position: 'absolute', right: 10, top: 8, padding: 8, background: 'rgba(18,20,22,0.85)', border: '1px solid var(--border)', borderRadius: 5, display: 'flex', flexDirection: 'column', gap: 3, minWidth: 140 }}>
                <div className="between"><span className="eyebrow">mode</span><span className="num">{data.mode}</span></div>
                <div className="between"><span className="eyebrow">ROI</span><span className={roi.startsWith('-') ? 'num c-neg' : 'num c-pos'}>{roi}</span></div>
                <div className="between"><span className="eyebrow">CLV</span><span className={clv.startsWith('-') ? 'num c-neg' : 'num c-pos'}>{clv}</span></div>
                <div className="between"><span className="eyebrow">capital</span><span className="num">{capital}</span></div>
              </div>
            </div>
            <div className="row" style={{ marginTop: 10, gap: 16, paddingTop: 10, borderTop: '1px solid var(--rule)' }}>
              <div className="col"><span className="eyebrow">turnover</span><span className="num" style={{ fontSize: 14 }}>{accepted} recs</span></div>
              <div className="col"><span className="eyebrow">mode</span><span className="num" style={{ fontSize: 14 }}>{data.mode}</span></div>
              <div className="col"><span className="eyebrow">capital deployed</span><span className="num" style={{ fontSize: 14 }}>{capital}</span></div>
              <div className="col"><span className="eyebrow">status</span><span className="num" style={{ fontSize: 14 }}>{data.enabled ? 'on' : 'off'}</span></div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--rule)' }}>
              <div className="between" style={{ marginBottom: 10 }}>
                <span className="eyebrow">decay monitor</span>
                <span className="chip warn"><span className="dot warn" />watch</span>
              </div>
              <div className="col" style={{ gap: 8 }}>
                <div className="between"><span style={{ fontSize: 12 }}>CLV</span><span className={clv.startsWith('-') ? 'num c-neg' : 'num c-pos'}>{clv}</span></div>
                <div className="bar"><i className={clv.startsWith('-') ? 'neg' : 'pos'} style={{ width: '62%' }} /></div>
                <div className="between"><span style={{ fontSize: 12 }}>paper ROI</span><span className={roi.startsWith('-') ? 'num c-neg' : 'num c-pos'}>{roi}</span></div>
                <div className="bar"><i className={roi.startsWith('-') ? 'neg' : 'acc'} style={{ width: '58%' }} /></div>
                <div className="between" style={{ marginTop: 4, paddingTop: 8, borderTop: '1px solid var(--rule)', fontSize: 12 }}>
                  <span className="c-muted">disarm threshold</span>
                  <span className="num c-warn">ECE &gt; 0.07 - 3 losers - DD &gt; -7%</span>
                </div>
              </div>
            </div>

            <div className="grow" style={{ padding: 16, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div className="between" style={{ marginBottom: 8 }}>
                <span className="eyebrow">last settled - {settled.length}</span>
                <span className="chip ghost c-muted">view all</span>
              </div>
              <div className="grow" style={{ overflow: 'auto' }}>
                <table className="tbl">
                  <colgroup>
                    <col style={{ width: 90 }} />
                    <col />
                    <col style={{ width: 70 }} />
                    <col style={{ width: 38 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Market</th>
                      <th className="num">CLV</th>
                      <th className="num">Res</th>
                    </tr>
                  </thead>
                  <tbody>
                    {settled.map((s: SettledBet, i: number) => (
                      <tr key={`${s.when}-${s.market}-${i}`} className="tbl-row" style={{ height: 28 }}>
                        <td className="c-muted num" style={{ fontSize: 11 }}>{s.when}</td>
                        <td>{s.market}</td>
                        <td className="num" style={{ color: `var(--${s.kind})` }}>{s.clv}</td>
                        <td className="num" style={{ color: `var(--${s.kind})`, fontWeight: 600 }}>{s.result}</td>
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
