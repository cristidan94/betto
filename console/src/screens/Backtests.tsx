import { ConsoleShell, type ScreenProps } from '../components/ConsoleShell'

export default function Backtests({ onNavigate, mode, onModeChange }: ScreenProps) {
  return (
    <ConsoleShell active="backtest" onNavigate={onNavigate} mode={mode} onModeChange={onModeChange}>
      <div style={{ display: 'grid', placeItems: 'center', height: '100%', padding: 24 }}>
        <div className="card" style={{ width: 'min(520px, 100%)', padding: 18, textAlign: 'center' }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>backtests</div>
          <h3 style={{ fontSize: 18, marginBottom: 6 }}>No backtest runs loaded</h3>
          <p className="c-muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
            Run a strategy backtest or connect Postgres to populate this view.
          </p>
        </div>
      </div>
    </ConsoleShell>
  )
}
