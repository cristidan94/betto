export interface StrategyKpi {
  label: string
  value: string
  hint: string
  kind: string | null
}

export interface SettledBet {
  when: string
  market: string
  clv: string
  result: string
  kind: string
}

export interface StrategyResponse {
  strategy_id: string
  name: string
  version: string
  mode: string
  enabled: boolean
  kpis: StrategyKpi[]
  settled: SettledBet[]
}
