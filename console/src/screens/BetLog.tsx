import { ConsoleShell, type Screen } from '../components/ConsoleShell'
import { Spark } from '../components/primitives'
import { useApi } from '../hooks/useApi'
import type { BetLogResponse, BetLogRow } from '../types/betlog'

function money(value: number) {
  const sign = value >= 0 ? '+' : '-'
  return `${sign}$${Math.abs(value).toFixed(2)}`
}

function pct(value: number) {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(1)}%`
}

export default function BetLog({ onNavigate }: { onNavigate: (s: Screen) => void }) {
  const { data, loading, error } = useApi<BetLogResponse>('/bets')

  if (loading) {
    return (
      <ConsoleShell active="log" onNavigate={onNavigate}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <span className="c-muted">Loading...</span>
        </div>
      </ConsoleShell>
    )
  }

  if (error || !data) {
    return (
      <ConsoleShell active="log" onNavigate={onNavigate}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <span className="c-neg">{error ?? 'Failed to load'}</span>
        </div>
      </ConsoleShell>
    )
  }

  const { summary, rows } = data

  return (
    <ConsoleShell active="log" onNavigate={onNavigate}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)' }}>
          <div className="between" style={{ marginBottom: 10 }}>
            <div className="col" style={{ gap: 4 }}>
              <span className="eyebrow">paper - 30 days - n = {summary.bets}</span>
              <h2 style={{ fontSize: 22, letterSpacing: '-0.01em', display: 'flex', alignItems: 'baseline', gap: 12 }}>
                Bet log
                <span className={summary.pnl_usd >= 0 ? 'num c-pos' : 'num c-neg'} style={{ fontSize: 14, fontWeight: 500 }}>{money(summary.pnl_usd)}</span>
                <span className={summary.mean_clv >= 0 ? 'num c-pos' : 'num c-neg'} style={{ fontSize: 14, fontWeight: 500 }}>CLV {pct(summary.mean_clv)}</span>
              </h2>
            </div>
            <div className="middle" style={{ gap: 8 }}>
              <span className="chip">staked <span className="num" style={{ color: 'var(--ink)', marginLeft: 4 }}>${summary.stake_usd.toLocaleString()}</span></span>
              <span className="chip">win rate <span className="num" style={{ color: 'var(--ink)', marginLeft: 4 }}>{pct(summary.hit_rate).replace('+', '')}</span></span>
              <div className="vr" style={{ height: 18 }} />
              <button className="chip" style={{ height: 26 }}>Export CSV</button>
              <button className="chip" style={{ height: 26 }}>Group by strategy</button>
            </div>
          </div>

          <div className="between">
            <div className="middle" style={{ gap: 8 }}>
              <div className="seg">
                <button className="on">all</button>
                <button>open</button>
                <button>settled</button>
                <button>skipped</button>
              </div>
              <span className="chip">paper</span>
              <span className="chip ghost c-muted">+ strategy</span>
              <span className="chip ghost c-muted">+ date</span>
            </div>
            <div className="middle" style={{ gap: 8 }}>
              <span className="eyebrow">cumulative CLV</span>
              <div style={{ width: 140, height: 28 }}><Spark w={140} h={28} seed={49} area /></div>
              <span className={summary.mean_clv >= 0 ? 'num c-pos' : 'num c-neg'}>{pct(summary.mean_clv)}</span>
            </div>
          </div>
        </div>

        <div className="grow" style={{ overflow: 'auto' }}>
          <table className="tbl" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: 120 }} />
              <col style={{ width: 120 }} />
              <col />
              <col style={{ width: 130 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 60 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 60 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 36 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 130 }} />
            </colgroup>
            <thead>
              <tr>
                <th>timestamp</th>
                <th>id</th>
                <th>market</th>
                <th className="num">model / mkt</th>
                <th className="num">edge</th>
                <th className="num">size</th>
                <th className="num">stake</th>
                <th>mode</th>
                <th>state</th>
                <th>res</th>
                <th className="num">CLV</th>
                <th>strategy</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: BetLogRow, i: number) => {
                const win = r.result === 'W'
                const lose = r.result === 'L'
                const skip = r.mode === 'skip'
                return (
                  <tr key={`${r.id}-${r.timestamp}-${i}`} className={`tbl-row ${skip ? 'dim' : ''}`} style={{ height: 28 }}>
                    <td className="c-muted num" style={{ fontSize: 11 }}>{r.timestamp}</td>
                    <td className="num" style={{ fontSize: 11, color: 'var(--ink-2)' }}>{r.id}</td>
                    <td style={{ fontSize: 12.5 }}>{r.market}</td>
                    <td className="num c-muted" style={{ fontSize: 11.5 }}>{r.model_market}</td>
                    <td className="num" style={{ color: r.edge >= 0 ? 'var(--pos)' : 'var(--neg)', fontWeight: 600 }}>
                      {pct(r.edge)}
                    </td>
                    <td className="num">{r.size === 0 ? <span className="c-dim">-</span> : (r.size * 100).toFixed(2) + '%'}</td>
                    <td className="num">{r.stake_usd === 0 ? <span className="c-dim">-</span> : '$' + r.stake_usd.toFixed(2)}</td>
                    <td>
                      <span className="badge" style={{
                        background: skip ? 'var(--surf-3)' : 'var(--acc-bg)',
                        color: skip ? 'var(--muted)' : 'var(--acc)',
                      }}>{r.mode}</span>
                    </td>
                    <td className="c-muted" style={{ fontSize: 11.5 }}>{r.state}</td>
                    <td className="num" style={{ color: win ? 'var(--pos)' : lose ? 'var(--neg)' : 'var(--dim)', fontWeight: 600 }}>{r.result}</td>
                    <td className="num" style={{ color: r.clv == null ? 'var(--dim)' : r.clv >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                      {r.clv == null ? '-' : (r.clv >= 0 ? '+' : '') + r.clv.toFixed(3)}
                    </td>
                    <td className="c-muted" style={{ fontSize: 11.5 }}>{r.strategy}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', padding: '12px 18px', borderTop: '1px solid var(--border)', background: 'var(--surf)' }}>
          {[
            ['Bets', String(summary.bets), null],
            ['Settled', String(summary.settled_bets), null],
            ['Open', String(summary.open_bets), null],
            ['Win rate', pct(summary.hit_rate).replace('+', ''), null],
            ['Settled P&L', money(summary.pnl_usd), summary.pnl_usd >= 0 ? 'pos' : 'neg'],
            ['CLV', pct(summary.mean_clv), summary.mean_clv >= 0 ? 'pos' : 'neg'],
          ].map((s, i) => (
            <div key={i} className="col" style={{ gap: 2 }}>
              <span className="eyebrow">{s[0]}</span>
              <span className="num" style={{ fontSize: 16, fontWeight: 600, color: s[2] === 'pos' ? 'var(--pos)' : s[2] === 'neg' ? 'var(--neg)' : 'var(--ink)' }}>{s[1]}</span>
            </div>
          ))}
        </div>
      </div>
    </ConsoleShell>
  )
}
