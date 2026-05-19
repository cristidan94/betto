export interface RiskKpi {
  label: string
  value: string
  hint: string
  kind: string | null
}

export interface CapitalBucket {
  name: string
  used: number
  cap: number
  state: string
  kind: string
}

export interface RiskCap {
  label: string
  value: string
  hint: string
}

export interface KillSwitch {
  name: string
  state: string
  trigger: string
  kind: string
}

export interface RiskResponse {
  kpis: RiskKpi[]
  buckets: CapitalBucket[]
  caps: RiskCap[]
  kill_switches: KillSwitch[]
}
