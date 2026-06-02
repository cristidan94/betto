export interface SourceOddsEntry {
  source: string
  prob: number
  best_bid: number | null
  best_ask: number | null
  bookmaker: string | null
}

export interface EdgeComparisonEntry {
  contest_id: string
  match: string
  market_type: string
  outcome: string
  model_prob: number | null
  polymarket_prob: number | null
  polymarket_volume: number | null
  oddspapi_prob: number | null
  oddspapi_bookmaker: string | null
  edge_vs_polymarket: number | null
  edge_vs_oddspapi: number | null
  edge_diff: number | null
  sources: SourceOddsEntry[]
}

export interface EdgeComparisonResponse {
  date: string
  comparisons: EdgeComparisonEntry[]
  markets_with_both_sources: number
  total_markets: number
}
