export interface BetLogSummary {
  bets: number
  settled_bets: number
  open_bets: number
  stake_usd: number
  pnl_usd: number
  roi: number
  mean_clv: number
  hit_rate: number
}

export interface BetLogRow {
  timestamp: string
  id: string
  market: string
  model_market: string
  edge: number
  size: number
  stake_usd: number
  mode: string
  state: string
  result: string
  clv: number | null
  strategy: string
}

export interface BetLogResponse {
  summary: BetLogSummary
  rows: BetLogRow[]
}
