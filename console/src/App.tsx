import { useState, useEffect } from 'react'
import type { Screen, BetMode } from './components/ConsoleShell'
import Today from './screens/Today'
import Recommendation from './screens/Recommendation'
import Matches from './screens/Matches'
import Strategies from './screens/Strategies'
import Backtests from './screens/Backtests'
import Ingestion from './screens/Ingestion'
import BetLog from './screens/BetLog'
import Risk from './screens/Risk'
import EdgeComparison from './screens/EdgeComparison'

const SCREEN_KEYS: Record<string, Screen> = {
  '1': 'today',
  '2': 'recs',
  '3': 'matches',
  '4': 'strats',
  '5': 'backtest',
  '6': 'ingest',
  '7': 'log',
  '8': 'risk',
  '9': 'edge',
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('today')
  const [mode, setMode] = useState<BetMode>('paper')

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

  const shellProps = { onNavigate: setScreen, mode, onModeChange: setMode }

  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      {screen === 'today' && <Today {...shellProps} />}
      {screen === 'recs' && <Recommendation {...shellProps} />}
      {screen === 'matches' && <Matches {...shellProps} />}
      {screen === 'strats' && <Strategies {...shellProps} />}
      {screen === 'backtest' && <Backtests {...shellProps} />}
      {screen === 'ingest' && <Ingestion {...shellProps} />}
      {screen === 'log' && <BetLog {...shellProps} />}
      {screen === 'risk' && <Risk {...shellProps} />}
      {screen === 'edge' && <EdgeComparison {...shellProps} />}
    </div>
  )
}
