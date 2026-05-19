# FE-BE Wiring: Console API Layer

**Date:** 2026-05-17
**Status:** Approved
**Scope:** Wire the first 3 screens (Today, Recommendation, Matches) to a FastAPI backend serving fixture data.

## Context

The betto console frontend has 8 React screens rendering hardcoded mock data. The Python backend has a rich domain layer (recommendations, Kelly sizing, paper evaluation, walk-forward backtesting, feature store, ingestion) but no HTTP API. This spec covers building the API bridge and replacing frontend mock data with real API calls for the core 3 screens.

## Decisions

- **Framework:** FastAPI (async, auto-OpenAPI, Pydantic models)
- **Data source:** Fixture JSON files extracted from existing hardcoded screen data
- **FE fetching:** Plain `fetch` + custom `useApi` hook (no external dependencies)
- **Scope:** Today, Recommendation, Matches screens (remaining 5 follow same pattern later)
- **Architecture:** Single FastAPI app, Vite proxy in dev, no provider abstraction yet

## API Structure

### Directory Layout

```
api/
  __init__.py
  main.py              # FastAPI app, CORS, mount routers
  routers/
    __init__.py
    today.py           # GET /api/today/recommendations
    recommendation.py  # GET /api/recommendations/{market_id}
    matches.py         # GET /api/matches, GET /api/matches/{match_id}/markets
  fixtures/
    today_recommendations.json
    recommendation_pm_cs_2891.json
    matches.json
    match_markets.json
  models/
    __init__.py
    today.py           # Pydantic response models for Today screen
    recommendation.py  # Pydantic response models for Recommendation screen
    matches.py         # Pydantic response models for Matches screen
```

### Endpoints

| Method | Path | Screen | Description |
|--------|------|--------|-------------|
| GET | `/api/today/recommendations` | Today | Filtered recommendation queue + summary stats |
| GET | `/api/recommendations/{rec_id}` | Recommendation | Full recommendation detail (rec_id = e.g. "PM-cs-2891--navi-ml") |
| GET | `/api/matches` | Matches | Today's match schedule with exposure/edge info |
| GET | `/api/matches/{match_id}/markets` | Matches detail | Markets for a specific match |

### Response Shapes

**GET /api/today/recommendations**
```json
{
  "summary": {
    "date": "2026-05-16",
    "surfaced": 14,
    "above_filter": 8,
    "would_stake_usd": 1810,
    "exposure_pct": 7.4,
    "exposure_cap_pct": 30.0
  },
  "recommendations": [
    {
      "id": "PM-cs-2891",
      "match": "NAVI vs G2",
      "market": "NAVI to win match",
      "model_prob": 0.583,
      "market_prob": 0.516,
      "edge": 0.067,
      "size": 0.0180,
      "confidence": "HIGH",
      "strategy": "map-winner v1",
      "close": "2h 14m",
      "veto": "open",
      "correlation": { "used": 4.2, "cap": 5.0 }
    }
  ]
}
```

**GET /api/recommendations/{rec_id}**
```json
{
  "id": "PM-cs-2891",
  "match": "NAVI vs G2",
  "market": "NAVI to win match",
  "strategy": "map-winner v1.4",
  "model_prob": 0.583,
  "market_prob": 0.516,
  "edge": 0.067,
  "size": 0.0180,
  "confidence": "HIGH",
  "stake_usd": 437.73,
  "close": "2h 14m",
  "format": "Bo3",
  "regime": "LAN",
  "veto": {
    "state": "open",
    "vetoed": 0,
    "total": 2,
    "maps": ["Mirage", "Anubis", "Nuke", "Inferno", "Ancient", "Dust2", "Vertigo"]
  },
  "derivatives": [
    {
      "market": "NAVI to win match",
      "model_prob": 0.583,
      "market_prob": 0.516,
      "edge": 0.067,
      "size": 0.0180,
      "state": "recommend"
    }
  ],
  "features": [
    { "label": "Team Elo delta", "value": 0.028 }
  ],
  "sizing_trace": [
    { "label": "Full Kelly", "value": 0.087, "applied": false },
    { "label": "x 1/4 fractional", "value": 0.0218, "applied": false },
    { "label": "capped at 2.5% / bet", "value": 0.0218, "applied": false },
    { "label": "correlated cap (per-match)", "value": 0.0180, "applied": true }
  ],
  "context": {
    "roster_navi": "stable 142d",
    "roster_g2": "stable 89d",
    "stand_ins": "none",
    "timezone_gap": "0h",
    "schedule": "NAVI d2, G2 d1",
    "news_24h": "none"
  },
  "strategy_health": {
    "clv_30d": 0.018,
    "paper_roi_30d": 0.032,
    "calibration_ece": 0.024,
    "drift_ece": 0.03,
    "days_since_refit": 9
  },
  "lineage": {
    "model": "map-winner-v1.4",
    "model_hash": "a8c3f1",
    "feature_snapshot": "09:42:18",
    "market_snapshot": "09:42:16",
    "backtest_run": 214
  }
}
```

**GET /api/matches**
```json
{
  "date": "2026-05-16",
  "matches": [
    {
      "id": "PM-cs-2891",
      "label": "NAVI vs G2",
      "tier": "T1",
      "format": "Bo3",
      "start": "13:56",
      "start_in": "2h 14m",
      "regime": "LAN",
      "veto": "open",
      "open_markets": 5,
      "recommendations": 2,
      "exposure_pct": 4.2,
      "best_edge": 0.067
    }
  ]
}
```

**GET /api/matches/{match_id}/markets**
```json
{
  "match_id": "PM-cs-2891",
  "markets": [
    {
      "market": "NAVI to win match",
      "edge": 0.067,
      "size": 0.0180,
      "state": "recommend"
    }
  ]
}
```

## Frontend Integration

### API Client (`console/src/api.ts`)

```ts
const BASE = '/api'

export async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
  return res.json()
}
```

### Data Hook (`console/src/hooks/useApi.ts`)

```ts
import { useState, useEffect } from 'react'
import { fetchJson } from '../api'

export function useApi<T>(path: string): {
  data: T | null
  loading: boolean
  error: string | null
} {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchJson<T>(path)
      .then((result) => { if (!cancelled) setData(result) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [path])

  return { data, loading, error }
}
```

### Screen Changes

Each screen:
1. Remove hardcoded `const` arrays
2. Add `useApi<ResponseType>(path)` call
3. Show loading text (`<span class="c-muted">Loading...</span>`) centered while fetching
4. Render from `data` instead of inline arrays
5. Type the response with a TypeScript interface matching the API response shape

### Types (`console/src/types/`)

One file per screen's API response type:
- `console/src/types/today.ts`
- `console/src/types/recommendation.ts`
- `console/src/types/matches.ts`

### Vite Proxy (`console/vite.config.ts`)

```ts
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

## Dev Workflow

**Two terminal processes:**
1. `cd api && uvicorn api.main:app --reload --port 8000`
2. `cd console && npm run dev`

Browser hits `localhost:5173`, Vite proxies `/api/*` to `localhost:8000`.

## Dependencies

**Python (add to pyproject.toml):**
- `fastapi`
- `uvicorn[standard]`

**Frontend:**
- None (plain fetch)

## CORS

FastAPI includes `CORSMiddleware` allowing `localhost:*` origins. In dev, the Vite proxy makes this mostly unnecessary, but it's there for direct API access or tools like Postman.

## Error Handling

- API: Standard HTTP status codes (404 for unknown IDs, 500 for unexpected errors)
- Frontend: `useApi` exposes `error` string; screens show error inline
- No retry logic this pass

## Future Extension Points

- Replace fixture JSON loading with real data source calls (same endpoint shapes)
- Add remaining 5 screens (Strategies, Backtests, Ingestion, BetLog, Risk) following identical pattern
- Add WebSocket for live market price updates on Today/Recommendation screens
- Add mutation endpoints (POST /api/recommendations/{rec_id}/accept, /skip, etc.)
