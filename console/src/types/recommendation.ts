export interface Derivative {
  market: string
  model_prob: number
  market_prob: number
  edge: number
  size: number
  state: string
}

export interface Feature {
  label: string
  value: number
}

export interface SizingStep {
  label: string
  value: number
  applied: boolean
}

export interface VetoState {
  state: string
  vetoed: number
  total: number
  maps: string[]
}

export interface MatchContext {
  roster_a: string
  roster_b: string
  stand_ins: string
  timezone_gap: string
  schedule: string
  news_24h: string
}

export interface StrategyHealth {
  clv_30d: number
  paper_roi_30d: number
  calibration_ece: number
  drift_ece: number
  days_since_refit: number
}

export interface Lineage {
  model: string
  model_hash: string
  feature_snapshot: string
  market_snapshot: string
  backtest_run: number
}

export interface RecommendationDetail {
  id: string
  match: string
  market: string
  strategy: string
  model_prob: number
  market_prob: number
  edge: number
  size: number
  confidence: string
  stake_usd: number
  close: string
  format: string
  regime: string
  veto: VetoState
  derivatives: Derivative[]
  features: Feature[]
  sizing_trace: SizingStep[]
  context: MatchContext
  strategy_health: StrategyHealth
  lineage: Lineage
}
