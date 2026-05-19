export interface MatchEntry {
  id: string
  label: string
  tier: string
  format: string
  start: string
  start_in: string
  regime: string
  veto: string
  open_markets: number
  recommendations: number
  exposure_pct: number
  best_edge: number
}

export interface MatchesResponse {
  date: string
  matches: MatchEntry[]
}

export interface MarketEntry {
  market: string
  edge: number
  size: number
  state: string
}

export interface MatchMarketsResponse {
  match_id: string
  markets: MarketEntry[]
}
