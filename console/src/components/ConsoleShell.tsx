import { type ReactNode } from 'react'
import { Logo, Status } from './primitives'

type Screen = 'today' | 'recs' | 'matches' | 'strats' | 'backtest' | 'ingest' | 'log' | 'risk'

const RAIL: [string, Screen, string, string | null][] = [
  ['1', 'today', 'Today', '14'],
  ['2', 'recs', 'Recommendations', null],
  ['3', 'matches', 'Matches', '6'],
  ['4', 'strats', 'Strategies', null],
  ['5', 'backtest', 'Backtests', null],
  ['6', 'ingest', 'Ingestion', null],
  ['7', 'log', 'Bet log', null],
  ['8', 'risk', 'Risk', null],
]

export function ConsoleShell({ active, children, crumb, onNavigate }: {
  active: Screen
  children: ReactNode
  crumb?: ReactNode
  onNavigate?: (screen: Screen) => void
}) {
  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', overflow: 'hidden' }}>
      {/* top bar */}
      <div style={{
        height: 44,
        display: 'flex',
        alignItems: 'center',
        gap: 18,
        padding: '0 16px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--surf)',
      }}>
        <Logo size={20} />
        <span className="badge" style={{ marginLeft: -6 }}>cs · v1</span>
        {crumb && (
          <span className="row" style={{ gap: 6, color: 'var(--muted)', fontSize: 12 }}>
            <span style={{ color: 'var(--dim)' }}>›</span>
            {crumb}
          </span>
        )}
        <div className="grow" />

        <div className="middle" style={{ gap: 18 }}>
          <div className="col" style={{ gap: 0, alignItems: 'flex-end' }}>
            <span className="num" style={{ fontSize: 14, color: 'var(--ink)' }}>$24,318.40</span>
            <span className="num c-pos" style={{ fontSize: 10.5 }}>+ $112.20 · 0.46%</span>
          </div>

          <div className="seg">
            <button className="on">Paper</button>
            <button>Live</button>
          </div>

          <span className="chip"><span className="dot ok" />Polymarket 2s</span>
          <span className="chip warn"><span className="dot warn" />drift · map-winner +0.03 ECE</span>

          <span className="middle" style={{ gap: 6, padding: '4px 10px', border: '1px solid var(--border)', borderRadius: 5, color: 'var(--muted)', fontSize: 11.5 }}>
            <span className="kbd">⌘</span><span className="kbd">K</span>
            <span>jump…</span>
          </span>
        </div>
      </div>

      {/* body */}
      <div style={{ display: 'flex', height: 'calc(100% - 44px)' }}>
        {/* left rail */}
        <div style={{
          width: 168,
          flex: '0 0 168px',
          borderRight: '1px solid var(--border)',
          background: 'var(--surf)',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{ padding: '12px 8px 4px' }}>
            <div className="eyebrow" style={{ padding: '0 8px 6px' }}>destinations</div>
            {RAIL.map((r) => {
              const on = r[1] === active
              return (
                <div
                  key={r[0]}
                  className="row"
                  onClick={() => onNavigate?.(r[1])}
                  style={{
                    position: 'relative',
                    alignItems: 'center',
                    gap: 8,
                    height: 28,
                    padding: '0 10px',
                    borderRadius: 5,
                    background: on ? 'var(--surf-3)' : 'transparent',
                    color: on ? 'var(--ink)' : 'var(--ink-2)',
                    marginBottom: 2,
                    cursor: 'pointer',
                  }}
                >
                  {on && <span className="active-rail" />}
                  <span className="kbd" style={{ borderColor: on ? 'var(--border-2)' : 'var(--border)' }}>{r[0]}</span>
                  <span style={{ fontSize: 12.5, fontWeight: on ? 600 : 400 }}>{r[2]}</span>
                  {r[3] && (
                    <span className="num" style={{
                      marginLeft: 'auto',
                      fontSize: 10.5,
                      background: on ? 'var(--acc-bg)' : 'var(--surf-2)',
                      color: on ? 'var(--acc)' : 'var(--muted)',
                      padding: '1px 5px',
                      borderRadius: 3,
                      lineHeight: 1.3,
                    }}>{r[3]}</span>
                  )}
                </div>
              )
            })}
          </div>

          <div className="grow" />

          <div style={{ padding: '10px 12px 8px', borderTop: '1px solid var(--rule)' }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>data plane</div>
            <div className="col" style={{ gap: 4 }}>
              <Status kind="ok">Polymarket · 2s</Status>
              <Status kind="ok">HLTV · 4m</Status>
              <Status kind="warn">Liquipedia · 18m</Status>
              <Status kind="ok">feature freshness</Status>
            </div>
          </div>
          <div style={{ padding: '8px 12px 10px', borderTop: '1px solid var(--rule)' }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>kill</div>
            <div className="row" style={{ gap: 6, alignItems: 'center' }}>
              <span className="dot acc" />
              <span style={{ fontSize: 12 }}>armed</span>
              <span className="c-muted" style={{ fontSize: 11, marginLeft: 'auto' }}>−2.1% dd</span>
            </div>
          </div>
        </div>

        {/* main */}
        <div className="grow" style={{ position: 'relative', overflow: 'hidden', background: 'var(--bg)' }}>
          {children}
        </div>
      </div>
    </div>
  )
}

export type { Screen }
