import { useState, useEffect, useRef } from 'react'
import { ConsoleShell, type ScreenProps } from '../components/ConsoleShell'
import { useApi } from '../hooks/useApi'
import type { MatchesResponse, MatchEntry, MatchMarketsResponse, MarketEntry } from '../types/matches'

export default function Matches({ onNavigate, mode, onModeChange }: ScreenProps) {
  const { data, loading, error } = useApi<MatchesResponse>('/matches')
  const [sel, setSel] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const shellProps = { mode, onModeChange }

  const matches = data?.matches ?? []
  const m = matches[sel]

  const { data: marketsData } = useApi<MatchMarketsResponse>(
    m ? `/matches/${m.id}/markets` : null
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
      if (['input', 'textarea'].includes(tag)) return
      if (e.key === 'j' || e.key === 'ArrowDown') { setSel(s => Math.min(matches.length - 1, s + 1)); e.preventDefault() }
      if (e.key === 'k' || e.key === 'ArrowUp') { setSel(s => Math.max(0, s - 1)); e.preventDefault() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [matches.length])

  useEffect(() => {
    if (sel >= matches.length) setSel(Math.max(0, matches.length - 1))
  }, [matches.length, sel])

  if (loading) {
    return (
      <ConsoleShell active="matches" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <span className="c-muted">Loading...</span>
        </div>
      </ConsoleShell>
    )
  }

  if (error || !data) {
    return (
      <ConsoleShell active="matches" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <span className="c-neg">{error ?? 'Failed to load'}</span>
        </div>
      </ConsoleShell>
    )
  }

  if (!m) {
    return (
      <ConsoleShell active="matches" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div style={{ padding: '14px 18px 10px', borderBottom: '1px solid var(--rule)' }}>
            <div className="col" style={{ gap: 2 }}>
              <span className="eyebrow">{data.date} - same-match exposure view</span>
              <h2 style={{ fontSize: 22, letterSpacing: '-0.01em', display: 'flex', alignItems: 'baseline', gap: 10 }}>
                Matches
                <span className="num c-muted" style={{ fontSize: 14, fontWeight: 500 }}>0 scheduled - 0 markets</span>
              </h2>
            </div>
          </div>
          <div className="grow" style={{ display: 'grid', placeItems: 'center', padding: 24 }}>
            <div className="card" style={{ width: 'min(520px, 100%)', padding: 18, textAlign: 'center' }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>schedule clear</div>
              <h3 style={{ fontSize: 18, marginBottom: 6 }}>No matches loaded</h3>
              <p className="c-muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
                The app has no current match rows from the configured data source.
              </p>
            </div>
          </div>
        </div>
      </ConsoleShell>
    )
  }

  const markets: MarketEntry[] = marketsData?.markets ?? [
    { market: 'Match-winner', edge: m.best_edge, size: m.exposure_pct / 100, state: m.recommendations > 0 ? 'recommend' : 'below filter' }
  ]

  return (
    <ConsoleShell active="matches" onNavigate={onNavigate} {...shellProps}>
      <div ref={rootRef} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 380px', height: '100%' }}>
        {/* schedule */}
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, borderRight: '1px solid var(--border)' }}>
          <div style={{ padding: '14px 18px 10px' }}>
            <div className="between" style={{ marginBottom: 8 }}>
              <div className="col" style={{ gap: 2 }}>
                <span className="eyebrow">{data.date} - same-match exposure view</span>
                <h2 style={{ fontSize: 22, letterSpacing: '-0.01em', display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  Matches
                  <span className="num c-muted" style={{ fontSize: 14, fontWeight: 500 }}>{matches.length} scheduled - {matches.reduce((s, x) => s + x.open_markets, 0)} markets</span>
                </h2>
              </div>
              <div className="middle" style={{ gap: 8 }}>
                <div className="seg">
                  <button className="on">today</button>
                  <button>+24h</button>
                  <button>week</button>
                </div>
                <span className="chip">Tier 1</span>
                <span className="chip ghost c-muted">+ filter</span>
              </div>
            </div>
          </div>

          <div className="grow" style={{ overflow: 'auto', borderTop: '1px solid var(--rule)' }}>
            <table className="tbl" style={{ tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: 38 }} />
                <col style={{ width: 92 }} />
                <col />
                <col style={{ width: 40 }} />
                <col style={{ width: 44 }} />
                <col style={{ width: 70 }} />
                <col style={{ width: 70 }} />
                <col style={{ width: 60 }} />
                <col style={{ width: 60 }} />
                <col style={{ width: 60 }} />
                <col style={{ width: 70 }} />
              </colgroup>
              <thead>
                <tr>
                  <th></th>
                  <th>Start (RO)</th>
                  <th>Match</th>
                  <th>Tier</th>
                  <th>Fmt</th>
                  <th>Regime</th>
                  <th>Veto</th>
                  <th className="num">Mkts</th>
                  <th className="num">Recs</th>
                  <th className="num">Exp%</th>
                  <th className="num">Best edge</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((row: MatchEntry, i: number) => {
                  const selected = i === sel
                  return (
                    <tr key={i} className={`tbl-row ${selected ? 'sel' : ''}`} onClick={() => setSel(i)} style={{ cursor: 'pointer', height: 32 }}>
                      <td><span className="idx">{(i + 1).toString().padStart(2, '0')}</span></td>
                      <td className="num" style={{ fontSize: 11 }}>
                        <div className="col" style={{ gap: 1 }}>
                          <span style={{ color: 'var(--ink-2)' }}>{row.start}</span>
                          <span className="c-muted" style={{ fontSize: 10 }}>{row.start_date}</span>
                        </div>
                      </td>
                      <td>
                        <div className="col" style={{ gap: 1 }}>
                          <span style={{ color: selected ? 'var(--ink)' : 'var(--ink-2)', fontWeight: selected ? 500 : 400 }}>{row.label}</span>
                          <span className="c-muted" style={{ fontSize: 10.5 }}>starts in {row.start_in}</span>
                        </div>
                      </td>
                      <td><span className="badge">{row.tier}</span></td>
                      <td className="num">{row.format}</td>
                      <td className="c-muted" style={{ fontSize: 11 }}>{row.regime}</td>
                      <td>
                        <span className="badge" style={{
                          background: row.veto === 'open' ? 'var(--pos-bg)' : row.veto === 'partial' ? 'var(--warn-bg)' : 'var(--surf-3)',
                          color: row.veto === 'open' ? 'var(--pos)' : row.veto === 'partial' ? 'var(--warn)' : 'var(--muted)',
                        }}>{row.veto}</span>
                      </td>
                      <td className="num">{row.open_markets}</td>
                      <td className="num" style={{ color: row.recommendations > 0 ? 'var(--acc)' : 'var(--dim)', fontWeight: 600 }}>{row.recommendations}</td>
                      <td className="num">
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ color: row.exposure_pct > 3 ? 'var(--acc)' : 'var(--ink-2)' }}>{row.exposure_pct.toFixed(1)}%</span>
                          <div style={{ width: 30, height: 4, background: 'var(--surf-3)', borderRadius: 2 }}>
                            <div style={{ width: `${(row.exposure_pct / 5) * 100}%`, height: '100%', background: row.exposure_pct > 3 ? 'var(--acc)' : 'var(--ink-2)', borderRadius: 2 }} />
                          </div>
                        </div>
                      </td>
                      <td className="num" style={{ color: row.best_edge >= 0.03 ? 'var(--pos)' : 'var(--muted)', fontWeight: row.best_edge >= 0.03 ? 600 : 500 }}>
                        {row.best_edge >= 0 ? '+' : ''}{(row.best_edge * 100).toFixed(1)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', padding: '8px 18px', borderTop: '1px solid var(--border)', background: 'var(--surf)', gap: 16, fontSize: 11.5, color: 'var(--muted)' }}>
            <span><span className="eyebrow" style={{ marginRight: 6 }}>selected</span><span className="num" style={{ color: 'var(--ink-2)' }}>{m.id}</span> - {m.label}</span>
            <span className="grow" />
            <span className="middle" style={{ gap: 6 }}>
              <span className="kbd">j</span><span className="kbd">k</span> step &nbsp;
              <span className="kbd">Enter</span> open markets &nbsp;
              <span className="kbd">x</span> exposure
            </span>
          </div>
        </div>

        {/* drilldown */}
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, padding: '14px 16px', gap: 14, overflow: 'auto' }}>
          <div className="col" style={{ gap: 6 }}>
            <span className="eyebrow"><span className="num">{m.id}</span></span>
            <h3 style={{ fontSize: 18, letterSpacing: '-0.01em' }}>{m.label}</h3>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              <span className="chip">{m.format} - {m.regime}</span>
              <span className="chip">starts {m.start_in}</span>
              <span className={`chip ${m.veto === 'open' ? 'pos' : m.veto === 'partial' ? 'warn' : ''}`}>
                <span className={`dot ${m.veto === 'open' ? 'ok' : m.veto === 'partial' ? 'warn' : 'idle'}`} />veto {m.veto}
              </span>
            </div>
          </div>

          <div className="card" style={{ padding: 12 }}>
            <div className="between" style={{ marginBottom: 6 }}>
              <span className="eyebrow">correlated cap - per-match 5%</span>
              <span className="num"><span className="c-acc">{m.exposure_pct.toFixed(1)}%</span><span className="c-muted">/5.0%</span></span>
            </div>
            <div className="bar" style={{ height: 10 }}>
              <i className="acc" style={{ width: `${(m.exposure_pct / 5) * 100}%` }} />
            </div>
            <div className="c-muted" style={{ fontSize: 11, marginTop: 6 }}>
              The cap is shared across every market on this match. Independent stakes get scaled down so the total cannot exceed 5% of bankroll.
            </div>
          </div>

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--rule)' }}>
              <span className="eyebrow">markets - {markets.length}</span>
            </div>
            <table className="tbl">
              <colgroup>
                <col />
                <col style={{ width: 70 }} />
                <col style={{ width: 60 }} />
                <col style={{ width: 70 }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Market</th>
                  <th className="num">Edge</th>
                  <th className="num">Size</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {markets.map((mk: MarketEntry, i: number) => (
                  <tr key={i} className={`tbl-row ${mk.state === 'recommend' ? 'sel' : ''}`} style={{ height: 28 }}>
                    <td style={{ fontSize: 12 }}>{mk.market}</td>
                    <td className="num" style={{ color: mk.edge >= 0 ? 'var(--pos)' : 'var(--neg)', fontWeight: 600 }}>
                      {(mk.edge >= 0 ? '+' : '') + (mk.edge * 100).toFixed(1)}%
                    </td>
                    <td className="num">{mk.size === 0 ? <span className="c-dim">-</span> : (mk.size * 100).toFixed(2) + '%'}</td>
                    <td>
                      <span className="badge" style={{
                        background: mk.state === 'recommend' ? 'var(--acc-bg)' : mk.state === 'opposite' ? 'var(--neg-bg)' : 'var(--surf-3)',
                        color: mk.state === 'recommend' ? 'var(--acc)' : mk.state === 'opposite' ? 'var(--neg)' : 'var(--muted)',
                      }}>{mk.state}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="col" style={{ gap: 8 }}>
            <span className="eyebrow">context</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 12, rowGap: 4, fontSize: 12 }}>
              <span className="c-muted">roster</span><span className="num">unknown</span>
              <span className="c-muted">stand-ins</span><span className="num">unknown</span>
              <span className="c-muted">starts (RO)</span><span className="num">{m.start_date} - {m.start}</span>
              <span className="c-muted">timezone</span><span className="num">Europe/Bucharest</span>
              <span className="c-muted">schedule</span><span className="num">{m.start_in}</span>
              <span className="c-muted">news - 24h</span><span className="num">unknown</span>
            </div>
          </div>
        </div>
      </div>
    </ConsoleShell>
  )
}
