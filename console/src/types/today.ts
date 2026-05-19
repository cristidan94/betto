export interface Correlation {
  used: number
  cap: number
}

export interface TodayRecommendation {
  id: string
  match: string
  market: string
  model_prob: number
  market_prob: number
  edge: number
  size: number
  confidence: string
  strategy: string
  close: string
  veto: string
  correlation: Correlation
  seed: number
}

export interface TodaySummary {
  date: string
  surfaced: number
  above_filter: number
  would_stake_usd: number
  exposure_pct: number
  exposure_cap_pct: number
}

export interface TodayResponse {
  summary: TodaySummary
  recommendations: TodayRecommendation[]
}
