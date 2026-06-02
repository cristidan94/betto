export interface IngestionSource {
  name: string
  kind: string
  fresh: string
  target: string
  cadence: string
  rows: number
  last_error: string
  on: boolean
}

export interface FeatureFreshness {
  name: string
  fresh: string
  kind: string
  rows: number
}

export interface IngestionResponse {
  sources: IngestionSource[]
  features: FeatureFreshness[]
  snapshot_lag: string
  snapshot_count: number
  schemas_ok: boolean
  leakage_tests_ok: boolean
}

export type IngestionAction =
  | 'migrate'
  | 'polymarket-cs'
  | 'polymarket-closed'
  | 'polymarket-price-history'
  | 'polymarket-account-history'
  | 'polymarket-reconcile'
  | 'polymarket-full-refresh'

export interface IngestionJobRequest {
  action: IngestionAction
  limit?: number
  max_pages?: number
  include_closed?: boolean
  closed_only?: boolean
  include_trades?: boolean
  timeout_sec?: number
}

export interface IngestionJobStep {
  command: string[]
  exit_code: number
  stdout: string
  stderr: string
  summary: unknown
}

export interface IngestionJobResponse {
  action: IngestionAction
  ok: boolean
  steps: IngestionJobStep[]
}
