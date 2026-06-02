import { ConsoleShell, type ScreenProps } from '../components/ConsoleShell'
import { useApi } from '../hooks/useApi'
import type { EdgeComparisonEntry, EdgeComparisonResponse } from '../types/edge_comparison'

function EmptyState({ children, onNavigate, mode, onModeChange, tone = 'muted' }: ScreenProps & { children: string; tone?: 'muted' | 'neg' }) {
  return (
    <ConsoleShell active="edge" onNavigate={onNavigate} mode={mode} onModeChange={onModeChange}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <span className={tone === 'neg' ? 'c-neg' : 'c-muted'}>{children}</span>
      </div>
    </ConsoleShell>
  )
}

function edgeColor(edge: number | null): string {
  if (edge === null) return 'var(--muted)'
  if (edge > 0.03) return 'var(--pos)'
  if (edge > 0) return 'var(--ink)'
  if (edge > -0.03) return 'var(--warn)'
  return 'var(--neg)'
}

function fmtProb(p: number | null): string {
  if (p === null) return '—'
  return p.toFixed(3)
}

function fmtEdge(e: number | null): string {
  if (e === null) return '—'
  return (e >= 0 ? '+' : '') + (e * 100).toFixed(1) + '%'
}

function fmtVol(v: number | null): string {
  if (v === null) return '—'
  if (v >= 1000) return '$' + (v / 1000).toFixed(1) + 'k'
  return '$' + v.toFixed(0)
}

function fmtType(t: string): string {
  return t.replace(/_/g, ' ')
}

export default function EdgeComparison({ onNavigate, mode, onModeChange }: ScreenProps) {
  const { data, loading, error } = useApi<EdgeComparisonResponse>('/edge-comparison')
  const shellProps = { mode, onModeChange }

  if (loading) return <EmptyState onNavigate={onNavigate} {...shellProps}>Loading...</EmptyState>
  if (error || !data) return <EmptyState onNavigate={onNavigate} {...shellProps} tone="neg">{error ?? 'Failed to load'}</EmptyState>

  if (data.comparisons.length === 0) {
    return (
      <ConsoleShell active="edge" onNavigate={onNavigate} {...shellProps}>
        <div style={{ display: 'grid', placeItems: 'center', height: '100%', padding: 24 }}>
          <div className="card" style={{ width: 'min(560px, 100%)', padding: 18, textAlign: 'center' }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>edge comparison</div>
            <h3 style={{ fontSize: 18, marginBottom: 6 }}>No cross-source data</h3>
            <p className="c-muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
              Ingest markets from both Polymarket and OddsAPI to see side-by-side odds comparison.
            </p>
          </div>
        </div>
      </ConsoleShell>
    )
  }

  return (
    <ConsoleShell active="edge" onNavigate={onNavigate} {...shellProps}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ padding: '14px 18px 12px', borderBottom: '1px solid var(--border)' }}>
          <div className="between">
            <div className="col" style={{ gap: 4 }}>
              <span className="eyebrow">polymarket vs traditional books</span>
              <h2 style={{ fontSize: 22 }}>
                Edge Comparison
                <span className="c-muted" style={{ fontWeight: 400, fontSize: 14, marginLeft: 10 }}>
                  {data.markets_with_both_sources} dual-source / {data.total_markets} total
                </span>
              </h2>
            </div>
          </div>
        </div>

        <div style={{ padding: '8px 18px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1, background: 'var(--border)', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden', margin: '12px 18px 0' }}>
          <div style={{ background: 'var(--surf)', padding: '10px 14px' }}>
            <span className="eyebrow">Markets tracked</span>
            <span className="num" style={{ display: 'block', fontSize: 20 }}>{data.total_markets}</span>
          </div>
          <div style={{ background: 'var(--surf)', padding: '10px 14px' }}>
            <span className="eyebrow">Both sources</span>
            <span className="num" style={{ display: 'block', fontSize: 20 }}>{data.markets_with_both_sources}</span>
          </div>
          <div style={{ background: 'var(--surf)', padding: '10px 14px' }}>
            <span className="eyebrow">Date</span>
            <span className="num" style={{ display: 'block', fontSize: 20 }}>{data.date}</span>
          </div>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '12px 18px' }}>
          <table className="console-table" style={{ width: '100%', fontSize: 12.5 }}>
            <thead>
              <tr>
                <th>Match</th>
                <th>Type</th>
                <th>Outcome</th>
                <th className="num">Model</th>
                <th className="num">PM prob</th>
                <th className="num">Book prob</th>
                <th className="num">PM edge</th>
                <th className="num">Book edge</th>
                <th className="num">Delta</th>
                <th className="num">PM vol</th>
              </tr>
            </thead>
            <tbody>
              {data.comparisons.map((row: EdgeComparisonEntry, i: number) => (
                <tr key={i}>
                  <td title={row.contest_id}>{row.match}</td>
                  <td>{fmtType(row.market_type)}</td>
                  <td>{row.outcome}</td>
                  <td className="num">{fmtProb(row.model_prob)}</td>
                  <td className="num">{fmtProb(row.polymarket_prob)}</td>
                  <td className="num" title={row.oddspapi_bookmaker ?? undefined}>{fmtProb(row.oddspapi_prob)}</td>
                  <td className="num" style={{ color: edgeColor(row.edge_vs_polymarket) }}>{fmtEdge(row.edge_vs_polymarket)}</td>
                  <td className="num" style={{ color: edgeColor(row.edge_vs_oddspapi) }}>{fmtEdge(row.edge_vs_oddspapi)}</td>
                  <td className="num" style={{ color: edgeColor(row.edge_diff) }}>{fmtEdge(row.edge_diff)}</td>
                  <td className="num">{fmtVol(row.polymarket_volume)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </ConsoleShell>
  )
}
