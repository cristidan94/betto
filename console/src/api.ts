import type { IngestionJobRequest, IngestionJobResponse } from './types/ingestion'

const BASE = '/api'

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}

export interface PlaceBetPayload {
  market_id: string
  outcome: string
  token_id?: string
  model_prob: number
  market_prob: number
  size_fraction: number
  mode: 'paper' | 'live'
}

export interface PlaceBetResult {
  success: boolean
  order_id: string
  mode: 'paper' | 'live'
  market_id: string
  outcome: string
  size_usd: number
  fill_price: number | null
  error: string | null
}

export function placeBet(payload: PlaceBetPayload): Promise<PlaceBetResult> {
  const mode = encodeURIComponent(payload.mode)
  return fetchJson<PlaceBetResult>(`/bets?mode=${mode}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function cancelBet(orderId: string): Promise<{ cancelled: boolean; order_id: string }> {
  return fetchJson<{ cancelled: boolean; order_id: string }>(`/bets/${encodeURIComponent(orderId)}`, {
    method: 'DELETE',
  })
}

export function runIngestionJob(payload: IngestionJobRequest): Promise<IngestionJobResponse> {
  return fetchJson<IngestionJobResponse>('/ingestion/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
