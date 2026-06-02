import { useState, useEffect, useRef } from 'react'
import { ConsoleShell, type ScreenProps } from '../components/ConsoleShell'
import { Spark, KellyTrace } from '../components/primitives'
import { useApi } from '../hooks/useApi'
import type { TodayResponse, TodayRecommendation } from '../types/today'
import { placeBet } from '../api'

export default function Today({ onNavigate, mode = 'paper', onModeChange }: ScreenProps) {
  const { data, loading, error } = useApi<TodayResponse>('/today/recommendations')
  const [sel, setSel] = useState(0)
  const [pendingBetId, setPendingBetId] = useState<string | null>(null)
  const [betStatus, setBetStatus] = useState<Record<string, string>>({})
  const rootRef = useRef<HTMLDivElement>(null)
  const shellProps = { mode, onModeChange }

  const recs = data?.recommendations ?? []

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
      if (['input', 'textarea'].includes(tag)) return
      const max = recs.length - 1
      if (e.key === 'j' || e.key === 'ArrowDown') { setSel(s => Math.min(max, s + 1)); e.preventDefault() }
      if (e.key === 'k' || e.key === 'ArrowUp') { setSel(s => Math.max(0, s - 1)); e.preventDefault() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [recs.length])

  useEffect(() => {
    if (sel >= recs.length) setSel(Math.max(0, recs.length - 1))
  }, [recs.length, sel])

  if (loading) {
    return (
      <ConsoleShell active="today" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <span className="c-muted">Loading...</span>
        </div>
      </ConsoleShell>
    )
  }

  if (error || !data) {
    return (
      <ConsoleShell active="today" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <span className="c-neg">{error ?? 'Failed to load'}</span>
        </div>
      </ConsoleShell>
    )
  }

  const r = recs[sel]
  if (!r) {
    return (
      <ConsoleShell active="today" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div style={{ padding: '14px 18px 10px', borderBottom: '1px solid var(--rule)' }}>
            <div className="between">
              <div className="col" style={{ gap: 2 }}>
                <span className="eyebrow">{data.summary.date} - CS v1</span>
                <h2 style={{ fontSize: 22, display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  Today
                  <span className="num c-muted" style={{ fontSize: 14, fontWeight: 500 }}>{data.summary.surfaced} surfaced</span>
                  <span className="num c-muted" style={{ fontSize: 14, fontWeight: 500 }}>{data.summary.above_filter} above filter</span>
                </h2>
              </div>
              <div className="middle" style={{ gap: 8 }}>
                <span className="chip"><span style={{ color: 'var(--muted)' }}>would stake</span> <span className="num" style={{ color: 'var(--ink)' }}>${data.summary.would_stake_usd.toLocaleString()}</span></span>
                <span className="chip"><span style={{ color: 'var(--muted)' }}>exposure</span> <span className="num" style={{ color: 'var(--ink)' }}>{data.summary.exposure_pct}%</span><span className="c-muted">/{data.summary.exposure_cap_pct}%</span></span>
              </div>
            </div>
          </div>
          <div className="grow" style={{ display: 'grid', placeItems: 'center', padding: 24 }}>
            <div className="card" style={{ width: 'min(520px, 100%)', padding: 18, textAlign: 'center' }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>queue clear</div>
              <h3 style={{ fontSize: 18, marginBottom: 6 }}>No current recommendations</h3>
              <p className="c-muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
                The app has no live or generated CS recommendations for this date.
              </p>
            </div>
          </div>
        </div>
      </ConsoleShell>
    )
  }
  const bankroll = Number(import.meta.env.VITE_BETTO_BANKROLL_USD ?? 0)
  const stake = r.size * bankroll
  const actionable = recs.filter((row) => row.size > 0 && row.edge > 0)

  const outcomeFor = (row: TodayRecommendation) => (
    row.outcome?.trim() || row.market.split(' - ').at(-1)?.trim() || row.market
  )

  const submitBet = async (row: TodayRecommendation) => {
    if (row.size <= 0) {
      setBetStatus((current) => ({ ...current, [row.id]: 'Blocked: no positive stake' }))
      return
    }
    if (mode === 'live' && !window.confirm(`Place LIVE bet on ${row.market}?`)) return

    setPendingBetId(row.id)
    setBetStatus((current) => ({ ...current, [row.id]: 'Sending...' }))
    try {
      const result = await placeBet({
        market_id: row.id,
        outcome: outcomeFor(row),
        token_id: row.token_id ?? '',
        model_prob: row.model_prob,
        market_prob: row.market_prob,
        size_fraction: row.size,
        mode,
      })
      setBetStatus((current) => ({
        ...current,
        [row.id]: result.success
          ? `${result.mode} bet placed: ${result.order_id || 'filled'}`
          : `Rejected: ${result.error ?? 'unknown error'}`,
      }))
    } catch (err) {
      setBetStatus((current) => ({
        ...current,
        [row.id]: err instanceof Error ? err.message : 'Bet request failed',
      }))
    } finally {
      setPendingBetId(null)
    }
  }

  const submitAll = async () => {
    for (const row of actionable) {
      await submitBet(row)
    }
  }

  return (
    <ConsoleShell active="today" onNavigate={onNavigate} {...shellProps}>
      <div ref={rootRef} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 360px', height: '100%' }}>
        {/* queue */}
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, borderRight: '1px solid var(--border)' }}>
          <div style={{ padding: '14px 18px 10px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="between">
              <div className="col" style={{ gap: 2 }}>
                <span className="eyebrow">{data.summary.date} - CS v1</span>
                <h2 style={{ fontSize: 22, letterSpacing: '-0.01em', display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  Today
                  <span className="num c-muted" style={{ fontSize: 14, fontWeight: 500 }}>{data.summary.surfaced} surfaced</span>
                  <span className="num c-acc" style={{ fontSize: 14, fontWeight: 500 }}>{data.summary.above_filter} above filter</span>
                </h2>
              </div>
              <div className="middle" style={{ gap: 8 }}>
                <span className="chip"><span style={{ color: 'var(--muted)' }}>would stake</span> <span className="num" style={{ color: 'var(--ink)' }}>${data.summary.would_stake_usd.toLocaleString()}</span></span>
                <span className="chip"><span style={{ color: 'var(--muted)' }}>exposure</span> <span className="num" style={{ color: 'var(--ink)' }}>{data.summary.exposure_pct}%</span><span className="c-muted">/{data.summary.exposure_cap_pct}%</span></span>
              </div>
            </div>

            <div className="between">
              <div className="middle" style={{ gap: 6 }}>
                <span className="eyebrow" style={{ marginRight: 4 }}>filter</span>
                <span className="chip acc">edge &gt;= 3%</span>
                <span className="chip">size &gt; 0</span>
                <span className="chip">veto open</span>
                <span className="chip ghost" style={{ color: 'var(--muted)' }}>+ add</span>
              </div>
              <div className="middle" style={{ gap: 8 }}>
                <span className="eyebrow">sort</span>
                <div className="seg">
                  <button className="on">edge</button>
                  <button>size</button>
                  <button>close</button>
                  <button>conf</button>
                </div>
                <div className="vr" style={{ height: 18 }} />
                <span className="middle" style={{ gap: 5, color: 'var(--muted)', fontSize: 12 }}>
                  <span className="kbd">j</span><span className="kbd">k</span> step
                </span>
                <span className="middle" style={{ gap: 5, color: 'var(--muted)', fontSize: 12 }}>
                  <span className="kbd">Enter</span> open
                </span>
              </div>
            </div>
          </div>

          <div className="grow" style={{ overflow: 'auto', borderTop: '1px solid var(--rule)' }}>
            <table className="tbl" style={{ tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: 38 }} />
                <col style={{ width: 138 }} />
                <col />
                <col style={{ width: 76 }} />
                <col style={{ width: 76 }} />
                <col style={{ width: 78 }} />
                <col style={{ width: 70 }} />
                <col style={{ width: 62 }} />
                <col style={{ width: 78 }} />
                <col style={{ width: 92 }} />
              </colgroup>
              <thead>
                <tr>
                  <th></th>
                  <th>Match</th>
                  <th>Market - strategy</th>
                  <th className="num">Model</th>
                  <th className="num">Mkt</th>
                  <th className="num">Edge</th>
                  <th className="num">Size</th>
                  <th>Conf</th>
                  <th>Close</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {recs.map((row: TodayRecommendation, i: number) => {
                  const selected = i === sel
                  const dim = row.size === 0 || row.edge < 0
                  return (
                    <tr key={i} className={`tbl-row ${selected ? 'sel' : ''} ${dim ? 'dim' : ''}`} onClick={() => setSel(i)} style={{ cursor: 'pointer', height: 'var(--row-h)' }}>
                      <td><span className="idx">{(i + 1).toString().padStart(2, '0')}</span></td>
                      <td><span style={{ color: selected ? 'var(--ink)' : 'var(--ink-2)', fontWeight: selected ? 500 : 400 }}>{row.match}</span></td>
                      <td>
                        <div className="col" style={{ gap: 1 }}>
                          <span style={{ color: selected ? 'var(--ink)' : 'var(--ink-2)' }}>
                            {row.market}
                            {row.veto === 'partial' && <span className="badge c-warn" style={{ marginLeft: 8, background: 'var(--warn-bg)' }}>veto pending</span>}
                          </span>
                          <span className="c-muted" style={{ fontSize: 10.5 }}>{row.strategy}</span>
                        </div>
                      </td>
                      <td className="num">{row.model_prob.toFixed(3)}</td>
                      <td className="num">{row.market_prob.toFixed(3)}</td>
                      <td className="num" style={{ color: row.edge >= 0 ? 'var(--pos)' : 'var(--neg)', fontWeight: 600 }}>
                        {(row.edge >= 0 ? '+' : '') + (row.edge * 100).toFixed(1) + '%'}
                      </td>
                      <td className="num">
                        {row.size === 0
                          ? <span className="c-dim">-</span>
                          : <span style={{ color: selected ? 'var(--acc)' : 'var(--ink-2)' }}>{(row.size * 100).toFixed(2)}%</span>}
                      </td>
                      <td>
                        <span className="badge" style={{
                          background: row.confidence === 'HIGH' ? 'var(--acc-bg)' : 'var(--surf-3)',
                          color: row.confidence === 'HIGH' ? 'var(--acc)' : 'var(--ink-2)',
                        }}>{row.confidence}</span>
                      </td>
                      <td className="c-muted">{row.close}</td>
                      <td>
                        <button
                          className={mode === 'live' ? 'chip neg' : 'chip acc'}
                          disabled={pendingBetId !== null || row.size <= 0}
                          onClick={(e) => {
                            e.stopPropagation()
                            void submitBet(row)
                          }}
                          style={{ height: 24, padding: '0 8px', fontSize: 11, opacity: row.size <= 0 ? 0.45 : 1 }}
                        >
                          {pendingBetId === row.id ? '...' : mode === 'live' ? 'Live' : 'Paper'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', padding: '8px 18px', borderTop: '1px solid var(--border)', background: 'var(--surf)', gap: 16, fontSize: 11.5, color: 'var(--muted)' }}>
            <span><span className="eyebrow" style={{ marginRight: 6 }}>selected</span><span className="num" style={{ color: 'var(--ink-2)' }}>{r.id}</span> - {r.market}</span>
            <span className="grow" />
            <span className="middle" style={{ gap: 6 }}>
              <span className="kbd">Enter</span> recommend &nbsp;
              <span className="kbd">Shift</span><span className="kbd">Enter</span> paper only &nbsp;
              <span className="kbd">s</span> skip &nbsp;
              <span className="kbd">f</span> filter
            </span>
            <button
              className={mode === 'live' ? 'chip neg' : 'chip acc'}
              disabled={pendingBetId !== null || actionable.length === 0}
              onClick={() => void submitAll()}
              style={{ height: 26, padding: '0 10px', fontSize: 11.5 }}
            >
              Bet All {actionable.length}
            </button>
          </div>
        </div>

        {/* detail rail */}
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, padding: '14px 16px', gap: 12, overflow: 'auto' }}>
          <div className="col" style={{ gap: 6 }}>
            <span className="eyebrow"><span className="num">{r.id}</span> - {r.strategy}</span>
            <h3 style={{ fontSize: 18, lineHeight: 1.2, letterSpacing: '-0.01em' }}>
              {r.match}
              <span className="c-muted" style={{ fontWeight: 400 }}> - </span>
              <span style={{ fontWeight: 400 }}>{r.market}</span>
            </h3>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              <span className={`chip ${r.edge >= 0.03 ? 'acc' : r.edge < 0 ? 'neg' : ''}`}>
                {r.edge >= 0 ? '+' : ''}{(r.edge * 100).toFixed(1)}% edge
              </span>
              <span className="chip">size {(r.size * 100).toFixed(2)}%</span>
              <span className="chip">1/4 Kelly</span>
              <span className="chip" style={{ color: r.veto === 'open' ? 'var(--pos)' : 'var(--warn)' }}>
                <span className={`dot ${r.veto === 'open' ? 'ok' : 'warn'}`} />veto {r.veto}
              </span>
            </div>
          </div>

          <div className="card" style={{ padding: 12 }}>
            <div className="between" style={{ marginBottom: 6 }}>
              <span className="eyebrow">market vs model - 24h</span>
              <span className="c-muted num" style={{ fontSize: 11 }}>2s ago</span>
            </div>
            <div style={{ height: 80 }}>
              <Spark w={310} h={80} seed={r.seed} model modelOffset={Math.min(0.18, Math.max(-0.05, r.edge * 2))} grid />
            </div>
            <div className="row" style={{ marginTop: 8, gap: 14 }}>
              <div className="col"><span className="eyebrow">model</span><span className="num c-acc">{r.model_prob.toFixed(3)}</span></div>
              <div className="col"><span className="eyebrow">market</span><span className="num">{r.market_prob.toFixed(3)}</span></div>
              <div className="col"><span className="eyebrow">edge</span><span className="num" style={{ color: r.edge >= 0 ? 'var(--pos)' : 'var(--neg)' }}>{(r.edge >= 0 ? '+' : '') + (r.edge * 100).toFixed(1)}%</span></div>
            </div>
          </div>

          <div className="card" style={{ padding: 12 }}>
            <div className="between" style={{ marginBottom: 10 }}>
              <span className="eyebrow">sizing trace</span>
              {r.size > 0 && <span className="num c-acc" style={{ fontSize: 14 }}>${stake.toFixed(2)}</span>}
            </div>
            {r.size > 0 ? (
              <KellyTrace
                rows={[
                  { label: 'Full Kelly', value: 0.087, applied: false },
                  { label: 'x 1/4 fractional', value: 0.0218, applied: false },
                  { label: 'capped at 2.5% / bet', value: 0.0218, applied: false },
                  { label: 'correlated cap (per-match)', value: r.size, applied: true },
                ]}
                max={0.10}
              />
            ) : (
              <span className="c-muted" style={{ fontSize: 12 }}>Filtered out - edge below threshold or correlated cap exhausted.</span>
            )}
          </div>

          <div className="card" style={{ padding: 12 }}>
            <div className="between" style={{ marginBottom: 8 }}>
              <span className="eyebrow">same-match exposure</span>
              <span className="num" style={{ fontSize: 11 }}>
                <span className="c-acc">{r.correlation.used.toFixed(1)}%</span>
                <span className="c-muted">/{r.correlation.cap.toFixed(0)}% cap</span>
              </span>
            </div>
            <div className="bar" style={{ height: 8, marginBottom: 10 }}>
              <i className="acc" style={{ width: `${(r.correlation.used / r.correlation.cap) * 100}%` }} />
            </div>
            <div className="col" style={{ gap: 5, fontSize: 11.5 }}>
              <div className="between"><span className="c-muted">{r.match}</span><span className="num">{r.correlation.used.toFixed(2)}%</span></div>
              <div className="between"><span className="c-muted">related market 1</span><span className="num">unknown</span></div>
              <div className="between"><span className="c-muted">related market 2</span><span className="num">unknown</span></div>
            </div>
          </div>

          <div className="col" style={{ gap: 6 }}>
            <span className="eyebrow">context</span>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              <span className="chip">context pending</span>
              <span className="chip">rosters unknown</span>
              <span className="chip">news unknown</span>
              <span className="chip">schedule unknown</span>
            </div>
          </div>

          <div className="grow" />

          {betStatus[r.id] && (
            <div className="card" style={{ padding: 10 }}>
              <div className="eyebrow" style={{ marginBottom: 4 }}>bet status</div>
              <span className={betStatus[r.id].startsWith('Rejected') || betStatus[r.id].startsWith('Blocked') ? 'c-neg' : 'c-muted'} style={{ fontSize: 12 }}>
                {betStatus[r.id]}
              </span>
            </div>
          )}

          <div className="row" style={{ gap: 8, paddingTop: 4 }}>
            <button
              className={mode === 'live' ? 'chip neg' : 'chip acc'}
              disabled={pendingBetId !== null || r.size <= 0}
              onClick={() => void submitBet(r)}
              style={{ height: 30, padding: '0 12px', fontSize: 12.5, justifyContent: 'center', flex: '1 1 auto', opacity: r.size <= 0 ? 0.5 : 1 }}
            >
              <span className="kbd" style={{ background: 'transparent', borderColor: 'var(--acc-ring)', color: 'var(--acc)' }}>Enter</span>
              Place {mode} ${r.size > 0 ? stake.toFixed(0) : '-'}
            </button>
            <button
              className="chip"
              onClick={() => onModeChange?.('paper')}
              style={{ height: 30, padding: '0 10px', fontSize: 12.5, justifyContent: 'center' }}
            >Paper</button>
            <button className="chip" style={{ height: 30, padding: '0 10px', fontSize: 12.5, justifyContent: 'center' }}>Skip</button>
          </div>
        </div>
      </div>
    </ConsoleShell>
  )
}
