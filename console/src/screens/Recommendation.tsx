import { useState } from 'react'
import { placeBet } from '../api'
import { ConsoleShell, type ScreenProps } from '../components/ConsoleShell'
import { useApi } from '../hooks/useApi'
import type { TodayRecommendation, TodayResponse } from '../types/today'

export default function Recommendation({ onNavigate, mode = 'paper', onModeChange }: ScreenProps) {
  const { data, loading, error } = useApi<TodayResponse>('/today/recommendations')
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [status, setStatus] = useState<string>('')
  const shellProps = { mode, onModeChange }
  const recs = data?.recommendations ?? []
  const rec = recs.find((row) => row.size > 0 && row.edge > 0) ?? recs[0]

  const outcomeFor = (row: TodayRecommendation) => (
    row.outcome?.trim() || row.market.split(' - ').at(-1)?.trim() || row.market
  )

  const submitBet = async (row: TodayRecommendation) => {
    if (row.size <= 0) {
      setStatus('Blocked: no positive stake')
      return
    }
    if (mode === 'live' && !window.confirm(`Place LIVE bet on ${row.market}?`)) return

    setPendingId(row.id)
    setStatus('Sending...')
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
      setStatus(result.success ? `${result.mode} bet placed: ${result.order_id || 'filled'}` : `Rejected: ${result.error ?? 'unknown error'}`)
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Bet request failed')
    } finally {
      setPendingId(null)
    }
  }

  if (loading) {
    return (
      <ConsoleShell active="recs" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'grid', placeItems: 'center', height: '100%', padding: 24 }}>
          <span className="c-muted">Loading...</span>
        </div>
      </ConsoleShell>
    )
  }

  if (error || !data) {
    return (
      <ConsoleShell active="recs" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'grid', placeItems: 'center', height: '100%', padding: 24 }}>
          <span className="c-neg">{error ?? 'Failed to load'}</span>
        </div>
      </ConsoleShell>
    )
  }

  if (!rec) {
    return (
      <ConsoleShell active="recs" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'grid', placeItems: 'center', height: '100%', padding: 24 }}>
          <div className="card" style={{ width: 'min(520px, 100%)', padding: 18, textAlign: 'center' }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>recommendations</div>
            <h3 style={{ fontSize: 18, marginBottom: 6 }}>No recommendations loaded</h3>
            <p className="c-muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
              Connect Postgres or generate recommendations to populate this view.
            </p>
          </div>
        </div>
      </ConsoleShell>
    )
  }

  const bankroll = Number(import.meta.env.VITE_BETTO_BANKROLL_USD ?? 0)
  const stake = rec.size * bankroll

  return (
    <ConsoleShell active="recs" onNavigate={onNavigate} {...shellProps}>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 340px', height: '100%' }}>
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)' }}>
            <div className="between">
              <div className="col" style={{ gap: 4 }}>
                <span className="eyebrow">recommendations - {recs.length} surfaced</span>
                <h2 style={{ fontSize: 22 }}>Recommendations</h2>
              </div>
              <span className={mode === 'live' ? 'chip neg' : 'chip acc'}>{mode}</span>
            </div>
          </div>

          <div className="grow" style={{ overflow: 'auto' }}>
            <table className="tbl" style={{ tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: 38 }} />
                <col />
                <col style={{ width: 80 }} />
                <col style={{ width: 80 }} />
                <col style={{ width: 80 }} />
                <col style={{ width: 76 }} />
              </colgroup>
              <thead>
                <tr>
                  <th></th>
                  <th>Market</th>
                  <th className="num">Model</th>
                  <th className="num">Mkt</th>
                  <th className="num">Edge</th>
                  <th className="num">Size</th>
                </tr>
              </thead>
              <tbody>
                {recs.map((row, i) => (
                  <tr key={`${row.id}-${i}`} className={`tbl-row ${row.id === rec.id ? 'sel' : ''} ${row.size <= 0 ? 'dim' : ''}`} style={{ height: 34 }}>
                    <td><span className="idx">{(i + 1).toString().padStart(2, '0')}</span></td>
                    <td>
                      <div className="col" style={{ gap: 1 }}>
                        <span>{row.match}</span>
                        <span className="c-muted" style={{ fontSize: 10.5 }}>{row.market}</span>
                      </div>
                    </td>
                    <td className="num">{row.model_prob.toFixed(3)}</td>
                    <td className="num">{row.market_prob.toFixed(3)}</td>
                    <td className="num" style={{ color: row.edge >= 0 ? 'var(--pos)' : 'var(--neg)', fontWeight: 600 }}>
                      {(row.edge >= 0 ? '+' : '') + (row.edge * 100).toFixed(1)}%
                    </td>
                    <td className="num">{row.size > 0 ? (row.size * 100).toFixed(2) + '%' : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ borderLeft: '1px solid var(--border)', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="col" style={{ gap: 6 }}>
            <span className="eyebrow">{rec.strategy}</span>
            <h3 style={{ fontSize: 18, lineHeight: 1.25 }}>{rec.match}</h3>
            <span className="c-muted" style={{ fontSize: 12 }}>{rec.market}</span>
          </div>
          <div className="card" style={{ padding: 12 }}>
            <div className="between"><span className="eyebrow">edge</span><span className="num c-pos">{(rec.edge * 100).toFixed(1)}%</span></div>
            <div className="between"><span className="eyebrow">stake</span><span className="num">${rec.size > 0 ? stake.toFixed(2) : '-'}</span></div>
            <div className="between"><span className="eyebrow">confidence</span><span className="num">{rec.confidence}</span></div>
          </div>
          {status && (
            <div className="card" style={{ padding: 10 }}>
              <div className="eyebrow" style={{ marginBottom: 4 }}>bet status</div>
              <span className={status.startsWith('Rejected') || status.startsWith('Blocked') ? 'c-neg' : 'c-muted'} style={{ fontSize: 12 }}>{status}</span>
            </div>
          )}
          <div className="grow" />
          <div className="row" style={{ gap: 8 }}>
            <button
              className={mode === 'live' ? 'chip neg' : 'chip acc'}
              disabled={pendingId !== null || rec.size <= 0}
              onClick={() => void submitBet(rec)}
              style={{ height: 30, padding: '0 12px', flex: '1 1 auto', justifyContent: 'center', opacity: rec.size <= 0 ? 0.5 : 1 }}
            >
              {pendingId === rec.id ? 'Sending...' : `Place ${mode}`}
            </button>
            <button className="chip" onClick={() => onModeChange?.('paper')} style={{ height: 30, padding: '0 10px' }}>Paper</button>
          </div>
        </div>
      </div>
    </ConsoleShell>
  )
}
