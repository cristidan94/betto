# CS2 Betting Edge System Design

Date: 2026-05-29

## Context

Build a CS2 betting system that scrapes HLTV data and places bets on Polymarket.
Layered edge strategy: data depth + speed + market structure exploitation.
Semi-automated execution (system recommends, human approves).
Starting bankroll under $5K — proving phase. First bets within 2-3 weeks.

## Edge Thesis

### Where The Edge Lives (Ranked)

**Tier 1 — Highest edge per effort**

1. **Map-specific team strength models** — Most bettors use global team ratings. Map-level Elo/Glicko is dramatically better because CS2 teams have wildly different strengths across maps. A team ranked #5 globally might be #25 on Ancient.
2. **Veto prediction → Expected map pool** — Predicting which maps will be played before the veto happens lets you price the series better than the market. Combined with map-level ratings, this is probably the single strongest feature.
3. **Roster disruption detection** — Stand-ins, new players, role swaps. Markets often don't reprice until late.

**Tier 2 — Strong but needs more data pipeline**

4. **Schedule fatigue / travel** — Maps played in last 72 hours, back-to-back matches, LAN vs online, travel between events.
5. **Form curves with opponent adjustment** — Form adjusted for opponent quality (strength-of-schedule) is signal; raw win rate is noise.
6. **Market data from Polymarket itself** — Opening line, current line, line movement, order book depth.

**Tier 3 — Unique but expensive to build**

7. **LLM-extracted qualitative signals** — Illness, confidence, practice issues from broadcasts/interviews.
8. **Demo-derived tactical features** — Positional matchups, site preference, execute patterns.

## System Gaps (Current State → Needed)

### Gap 1: No Prediction Model Layer

- Rating system (Elo/Glicko-2, per-team per-map, time-decayed)
- Feature engineering (point-in-time features, no future leakage)
- Model training (start with logistic regression on strong features)
- Calibration verification

### Gap 2: No Polymarket Integration

- Odds scraping (current prices, order book depth, historical lines)
- Edge calculation (model probability vs implied probability)
- Order preparation (pre-built orders for one-click execution)

### Gap 3: No Backtesting Framework

- Point-in-time feature snapshots
- Simulated betting over historical data
- CLV (Closing Line Value) analysis

### Gap 4: No Live Pipeline

- Upcoming match discovery (not just results)
- Pre-match feature computation
- Edge alert system

## Phased Implementation

### Phase 1: First Bets (Weeks 1-3)

Build the minimum loop: data → model → signal → manual bet.

1. **Map-level Glicko-2 rating engine** — Process all historical fixtures into per-team per-map ratings. Update after every new result.
2. **Match probability calculator** — Given two teams, best-of format, and predicted map pool: simulate veto → map picks → map outcomes → series result.
3. **Polymarket odds scraper** — Fetch current prices and order book depth for CS2 match markets. Store historically.
4. **Edge detector + daily digest** — Compare model vs market. Alert: match, model price, market price, edge %, Kelly stake.
5. **Simple backtest** — Last 6 months: accuracy, calibration, simulated ROI, CLV.

### Phase 2: Sharpen The Edge (Weeks 3-6)

6. **Veto prediction model** — Predict which maps get played from historical ban/pick patterns. Feed into series probability.
7. **Roster change detection** — Compare rosters over time. Flag affected matches, apply disruption discount.
8. **Form and recency features** — Exponentially weighted recent performance, rest/rust, fatigue (maps in 72h).
9. **Opponent-adjusted strength of schedule** — Adjust form by opponent rating.
10. **Bet tracker + P&L dashboard** — Log bets, track ROI, CLV, edge realization, bankroll curve.

### Phase 3: Widen The Moat (Months 2-3)

11. **Correct score and total maps markets** — Map-level model produces these naturally.
12. **LLM news/broadcast signal extraction** — HLTV news, Reddit, Twitter → structured claims with confidence + timestamp.
13. **Event context features** — LAN/online, elimination, grand final, travel distance.
14. **Line movement signals** — Track odds movement pre-match. Sharp movement = info; stale lines = opportunity.
15. **Automated order builder** — Pre-built Polymarket orders with computed stake. One-click submit.

### Explicitly Deferred

- Demo parsing — high effort, marginal over map-level ratings for match winner markets
- Player-level prop models — Polymarket likely doesn't offer these
- Full auto-execution — not worth the risk at <$5K; reviewing each bet builds intuition

## Data Requirements For The Model

Every feature must be computable from data known **before** match start. The scraper must provide:

### Already Captured
- Match results with map scores
- Per-map player stats (kills, deaths, ADR, rating, KAST, HS%, FK/FD)
- Veto sequences (ban/pick order, team, map)
- Event metadata (name, tier, stars)
- Match scheduled time and best-of format
- Team and player IDs

### Newly Added (This Session)
- Event pages: location, country, LAN/online, prize pool, dates, teams
- Team pages: roster, coach, country, world ranking, map win/loss
- Player pages: country, age, rating, ADR, KAST, impact, KPR, HS%
- Stats error tracking for reliability

### Still Needed For Phase 1
- **Upcoming matches** — Discover scheduled/upcoming matches, not just results
- **Historical team rankings** — Weekly HLTV rankings over time for rank-at-match-time
- **Head-to-head records** — Direct matchup history between two teams
- **Half scores** — CT/T side scores per map (available on match pages but not yet parsed)
- **Overtime detection** — Whether a map went to overtime

### Still Needed For Phase 2+
- Polymarket API integration (odds, order book, order placement)
- HLTV news page scraping
- Social media signal collection (Reddit, Twitter)
