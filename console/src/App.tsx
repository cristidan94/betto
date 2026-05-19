import { useState, useEffect } from 'react'
import type { Screen } from './components/ConsoleShell'
import Today from './screens/Today'
import Recommendation from './screens/Recommendation'
import Matches from './screens/Matches'
import Strategies from './screens/Strategies'
import Backtests from './screens/Backtests'
import Ingestion from './screens/Ingestion'
import BetLog from './screens/BetLog'
import Risk from './screens/Risk'

const SCREEN_KEYS: Record<string, Screen> = {
  '1': 'today',
  '2': 'recs',
  '3': 'matches',
  '4': 'strats',
  '5': 'backtest',
  '6': 'ingest',
  '7': 'log',
  '8': 'risk',
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('today')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
      }
      if (e.altKey && SCREEN_KEYS[e.key]) {
        setScreen(SCREEN_KEYS[e.key])
        e.preventDefault()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      {screen === 'today' && <Today onNavigate={setScreen} />}
      {screen === 'recs' && <Recommendation onNavigate={setScreen} />}
      {screen === 'matches' && <Matches onNavigate={setScreen} />}
      {screen === 'strats' && <Strategies onNavigate={setScreen} />}
      {screen === 'backtest' && <Backtests onNavigate={setScreen} />}
      {screen === 'ingest' && <Ingestion onNavigate={setScreen} />}
      {screen === 'log' && <BetLog onNavigate={setScreen} />}
      {screen === 'risk' && <Risk onNavigate={setScreen} />}
    </div>
  )
}
