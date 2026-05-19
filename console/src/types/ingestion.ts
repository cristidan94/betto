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
