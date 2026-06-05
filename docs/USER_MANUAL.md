# Betto — The Complete User Manual

*Written so that someone who has never used a computer terminal before can follow it.*
*Last updated: 2026-06-05.*

---

## Table of contents

1. [What is Betto, in plain words](#1-what-is-betto-in-plain-words)
2. [The three parts of the system (and how they fit together)](#2-the-three-parts-of-the-system)
3. [Getting in: how to open the console](#3-getting-in-how-to-open-the-console)
4. [A guided tour of every screen](#4-a-guided-tour-of-every-screen)
5. [Paper mode vs Live mode (read this before betting)](#5-paper-mode-vs-live-mode)
6. [The big journey: how raw data becomes a betting tip](#6-the-big-journey-how-raw-data-becomes-a-betting-tip)
7. [How to do ingestion (loading data)](#7-how-to-do-ingestion-loading-data)
8. [How to run a backtest](#8-how-to-run-a-backtest)
9. [What "strategies" are](#9-what-strategies-are)
10. [How to read and use recommendations](#10-how-to-read-and-use-recommendations)
11. [The exact state of YOUR system right now](#11-the-exact-state-of-your-system-right-now)
12. [Glossary (every word explained)](#12-glossary)
13. [Cheat sheet & troubleshooting](#13-cheat-sheet--troubleshooting)

---

## 1. What is Betto, in plain words

Betto is a tool that helps you bet on **Counter-Strike** (a video game played in professional tournaments) **more intelligently**.

Here is the whole idea in one sentence:

> Betto looks at the history of how teams have played, makes its own guess about who will win, compares that guess to the prices people are betting at on a website called **Polymarket**, and tells you when the price looks *wrong in your favour*.

When a price is wrong in your favour, that is called an **edge**. If Betto thinks Team A has a 60% chance to win, but the betting market is pricing them as if they only have a 50% chance, that 10% gap is the edge. Betting on edges, over and over, is how you make money in the long run — the same way a casino makes money: not by winning every hand, but by always having a small advantage.

Betto does **not** guarantee wins. It is a disciplined assistant, not a crystal ball. Its job is to find small advantages and to stop you from betting too much on any one game.

---

## 2. The three parts of the system

Think of Betto like a **restaurant**:

| Part | Restaurant analogy | What it really is | Where it lives |
|------|--------------------|-------------------|----------------|
| **The database** | The pantry & fridge — where all the ingredients are stored | A program called **PostgreSQL** that stores every match, team, market and price | Port **5432** on this server |
| **The API** | The kitchen — takes ingredients and cooks dishes to order | A program (**FastAPI**) that reads the database and answers questions like "what matches are today?" | Port **8000** on this server |
| **The console** | The dining room — where you sit and read the menu | The **website** you actually look at, with screens and tables | Port **5173** on this server |

You, the user, only ever look at the **console** (the dining room). The console asks the **API** (the kitchen) for information, and the API gets it from the **database** (the pantry). You never touch the database directly.

There is also a fourth helper, the **scraper**, which is like the delivery truck that goes out to the website **HLTV.org** every night and brings back fresh match results to put in the pantry. It runs on its own, automatically.

> **A "port" is just a numbered door on the server.** The database lives behind door 5432, the kitchen behind door 8000, the dining room behind door 5173. You walk through door 5173 to use Betto.

---

## 3. Getting in: how to open the console

The console runs on the server, but for safety it is **locked to the server itself** — you cannot reach it just by typing an address into your browser. (This is on purpose: the console can place real-money bets, so we don't want it open to the whole internet.)

To reach it from your own laptop, you build a private tunnel using a command called **SSH**. You only need to do this once each time you sit down to work.

**On your own laptop**, open a terminal and type this (replace `SERVER_ADDRESS` with the server's address):

```bash
ssh -L 5173:localhost:5173 -L 8000:localhost:8000 ubuntu@SERVER_ADDRESS
```

What this does, in plain words: *"Connect me to the server, and make the server's door 5173 and door 8000 appear as if they were on my own laptop."*

Leave that terminal window open. Now open your web browser and go to:

```
http://localhost:5173
```

You should see the Betto console. 🎉

> **If the page does not load**, the kitchen or dining room may not be running. See the [cheat sheet](#13-cheat-sheet--troubleshooting) for how to start them.

---

## 4. A guided tour of every screen

Down the left side of the console is a menu (we call it the **rail**). Each item has a number — you can press that number key on your keyboard to jump straight to it. There are nine screens.

At the very top-right there is a **Paper / Live** switch. **Leave it on "Paper"** for now — see [section 5](#5-paper-mode-vs-live-mode).

### 1 — Today
Your morning headline. It shows the bets Betto is suggesting **for today**, how much money it would put on them, and the total risk. If Betto has nothing to suggest, this screen is quiet — that is normal and correct, not a bug.

### 2 — Recommendations
The full list of every betting suggestion Betto has produced (not just today's). Click one to open its detail page, which shows *why* Betto likes it: its predicted probability, the market's price, the resulting edge, and how big a bet it recommends.

### 3 — Matches
The schedule of Counter-Strike matches. Each row is one match (Team A vs Team B) with:

- **Start (RO)** — the date and kick-off time **in Romanian time** (Europe/Bucharest). *This was set up specifically for you, so you never have to convert time zones in your head.*
- **Mkts** — how many betting markets (from Polymarket) are attached to this match.
- **Recs** — how many recommendations Betto made for it.
- **Exp%** — how much of your bankroll is exposed to this match.
- **Best edge** — the best advantage Betto found.

Click any match to open a panel on the right showing its markets and a **5%-per-match exposure cap** (Betto will never let you risk more than 5% of your money on a single match).

> The list is sorted so that matches **that have markets attached show up first**, then the most recent matches. That way the useful rows are always at the top.

### 4 — Strategies
A **strategy** is a complete recipe for betting (which model to trust, how big to bet, when to skip a bet). This screen shows each strategy's health: how many recommendations it made, how accurate it has been, and its profit-per-bet. See [section 9](#9-what-strategies-are).

### 5 — Backtests
A **backtest** is a time machine. It replays history and asks: *"If I had used this strategy in the past, would I have made money?"* This screen lists those replays and their results. See [section 8](#8-how-to-run-a-backtest).

### 6 — Ingestion
Your **data control panel**. It shows which data sources are loaded, how fresh they are, how many price snapshots exist, and whether safety checks pass. You can also start new data-loading jobs from here. See [section 7](#7-how-to-do-ingestion-loading-data).

### 7 — Bet log
The diary of every bet placed (paper or real): what you bet, how much, and whether it won or lost. Empty until you place bets.

### 8 — Risk
The safety dashboard. It shows how much of your money is at stake, the caps that protect you, and the **kill switches** (emergency stops that halt betting if something goes wrong).

### 9 — Edge compare
A price-comparison screen. For each market it lines up **Betto's model price**, the **Polymarket price**, and (if available) a **bookmaker price**, so you can see who is offering the best deal and where the edge is biggest.

---

## 5. Paper mode vs Live mode

At the top of the console is a switch with two settings:

- **Paper** (the safe default): every bet is **pretend**. No real money moves. This is a flight simulator — you can practise, test strategies and learn with zero risk.
- **Live**: every bet uses **real money** on Polymarket. The switch turns red and asks you to confirm, because mistakes here cost real money.

**Rule of thumb:** stay in **Paper** until you have (a) run backtests you trust, (b) watched paper bets settle profitably for a while, and (c) connected your Polymarket account. Live mode also requires account credentials that are **not yet set up** on this system (see section 11).

---

## 6. The big journey: how raw data becomes a betting tip

This is the heart of the platform. A recommendation does not appear by magic — it is the end of an assembly line with seven stations. Understanding this line explains *everything* about why screens are full or empty.

```
  (1) INGEST        (2) LINK          (3) FEATURES      (4) MODEL
  Load matches &    Connect each      Turn history      Learn from history
  market prices --> betting market --> into numbers  --> to predict who
  into the pantry   to its match       (win rates...)    wins (a probability)
                                                              |
                                                              v
  (7) BET           (6) RECOMMEND     (5) BACKTEST
  Place the bet  <-- Compare model  <-- Replay the past to
  (paper or live)   price vs market    check the strategy
                    -> find the edge   actually makes money
```

1. **Ingest** — bring raw data in: HLTV match results, Polymarket markets, Polymarket prices.
2. **Link** — connect each Polymarket betting market to the exact HLTV match it refers to. *(This is the step the new `db-link-polymarket-markets` command performs.)*
3. **Features** — convert messy history into clean numbers a model can use (e.g. "this team wins 64% of its matches on the map Mirage").
4. **Model** — a program studies those numbers and learns to output a **probability** for each side of a match.
5. **Backtest** — before trusting the model, replay the past and confirm the strategy would have profited.
6. **Recommend** — compare the model's probability to the market's price. If the gap (edge) is big enough and passes the safety filters, it becomes a recommendation.
7. **Bet** — log the bet, in paper mode or for real.

**Why this matters:** if a later station has no input, its screen is empty. Right now your system has completed stations 1 and 2, so **Matches** and **Edge compare** have data, but stations 3–7 have not been run yet, so **Recommendations, Strategies, Backtests, Bet log** are empty. That is expected, not broken. Sections 7–10 tell you how to run the remaining stations.

> **Where you type these commands:** in the SSH terminal from section 3, first move into the project folder. From then on, every command starts with `.venv/bin/python -m core.cli.main`:
>
> ```bash
> cd /opt/betto/repo
> ```
>
> The database is already configured, so you do not need to set anything up first.

---

## 7. How to do ingestion (loading data)

Ingestion = putting ingredients in the pantry. There are a few sources. You can run these from the **Ingestion** screen, or by typing commands. The commands are shown here because they are precise and repeatable. Every command is **idempotent** — running it twice does no harm; it just updates.

### 7a. HLTV match history (the foundation)
The nightly scraper saves match files to a folder. Load them into the database with:

```bash
.venv/bin/python -m core.cli.main db-ingest-hltv-scraped --scraped-dir /opt/betto/scraper/data/hltv_scraped
```

This loads matches, teams, players, map results and map vetoes. *(Already done on your system: ~4,388 matches.)*

### 7b. Polymarket markets (the things you bet on)
Two commands — one for markets that are still open, one for markets that already closed:

```bash
# Currently open Counter-Strike markets
.venv/bin/python -m core.cli.main db-ingest-polymarket-cs

# Historical (closed) Counter-Strike markets
.venv/bin/python -m core.cli.main db-backfill-polymarket-cs-closed
```

### 7c. Polymarket prices (how the odds moved over time)
For each market, pull the history of its price:

```bash
.venv/bin/python -m core.cli.main db-ingest-polymarket-price-history
```

*(Already done: ~35,000 price snapshots.)*

### 7d. **Linking markets to matches** (the new step)
A Polymarket market like *"IEM Cologne: 3DMAX vs. TYLOO"* is just text until we connect it to the actual HLTV match. This command does that connection by reading the team names out of each market's title and finding the matching match:

```bash
# First, do a DRY RUN — this shows what WOULD be linked, but changes nothing:
.venv/bin/python -m core.cli.main db-link-polymarket-markets --dry-run

# Happy with the result? Run it for real:
.venv/bin/python -m core.cli.main db-link-polymarket-markets
```

It is deliberately **careful**: it skips markets from other games (Dota 2, Valorant), skips tournament-winner bets that have no single opponent, and refuses to link a market to a match that happened months away from when the market was created (which would be the wrong meeting between the same two teams). You can loosen or tighten this:

- `--min-confidence 0.8` — how sure it must be (0.95 = team names *and* dates line up; 0.8 = names line up).
- `--max-day-gap 2` — reject a link if the nearest matching match is more than this many days from the market's date.

> **Honest note about your data:** only a handful of Polymarket markets currently link, because the Polymarket markets we have and the HLTV matches we have mostly come from *different* events. This is a data-coverage reality, not a failure. As more overlapping data is ingested, more will link automatically.

### 7e. Checking your work
On the **Ingestion** screen, or with:

```bash
.venv/bin/python -m core.cli.main db-check          # is the database reachable?
```

---

## 8. How to run a backtest

A **backtest** answers the single most important question before risking money: *"Does this strategy actually work?"*

It works by **walk-forward validation** — the honest way to test. Imagine standing at a date in the past:

1. Let the model learn **only** from matches *before* that date (the "training" window).
2. Ask it to predict matches in the *next* couple of weeks (the "validation" window) — games it has never seen.
3. Score how right it was.
4. Step forward two weeks and repeat.

This mimics real life, where you can only ever learn from the past. (A dishonest backtest would let the model peek at the answers — Betto specifically avoids that.)

First, turn history into numbers (features), then run the walk-forward:

```bash
# Step 1: build features as of a date, from a set of match files
.venv/bin/python -m core.cli.main db-materialize-cs-features \
  --as-of 2026-02-20T00:00:00Z \
  --fixtures /path/to/match1.json /path/to/match2.json

# Step 2: walk-forward backtest over a date range
.venv/bin/python -m core.cli.main db-walk-forward-cs-baseline \
  --corpus /path/to/match/folder \
  --start 2026-01-01 --end 2026-02-15 \
  --train-days 30 --validate-days 14 --step-days 14
```

The results appear on the **Backtests** screen. The numbers to look at:

- **Brier score** and **log loss** — how accurate the probabilities are (**lower is better**).
- **Mean edge** — the average advantage found.
- **Max drawdown** — the worst losing streak (how much you'd have been down at the lowest point).

There is also a one-shot report that runs the model, applies the betting filters, and prints a readiness verdict:

```bash
.venv/bin/python -m core.cli.main db-report-cs-baseline-strategy \
  --corpus /path/to/match/folder \
  --markets /path/to/market/folder \
  --compact
```

---

## 9. What "strategies" are

A **strategy** is the full rulebook that turns a prediction into a bet. It bundles four decisions:

1. **The model** — whose prediction do we trust? (The current one is the **baseline** model, which uses map win-rates and recent form. "Baseline" means *simple and dependable*, the bar that fancier models must beat.)
2. **The edge filter** — how big must the advantage be before we bet? (e.g. `--min-edge 0.03` = only bet when our edge is at least 3%.)
3. **The bet size** — how much to stake. Betto uses a careful version of the **Kelly criterion**, a famous formula that bets *more* when the edge is large and your confidence is high, and *less* when it is thin. It also caps any single match at **5% of bankroll** and the whole day at a set fraction.
4. **The safety gates** — accuracy must be good enough (Brier/log-loss thresholds), the losing streaks small enough, and enough sample size to be meaningful. If any gate fails, the strategy is marked **not ready** and stops suggesting bets.

The console ships with a strategy called **`map-winner`** (shown on the **Strategies** screen). You can have several strategies and compare them. A strategy only starts producing recommendations once it has been run and passes its readiness gates.

---

## 10. How to read and use recommendations

This is the payoff — the screen you will use most. Open **Recommendations** (or **Today**) and click one. Here is how to read it.

**The core question every recommendation answers:** *"Is the market's price cheaper than the true odds?"*

Key fields:

| Field | What it means | How to read it |
|-------|---------------|----------------|
| **Model prob** | Betto's estimate of the chance this outcome happens | e.g. `0.60` = 60% likely |
| **Market price** | What Polymarket is charging — also read as a probability | e.g. `0.50` = market thinks 50% |
| **Edge** | Model prob − market price | `+0.10` (+10%) = the advantage. Bigger = better |
| **Size / stake** | How much to bet, as a % of bankroll (and in dollars) | Set by the Kelly formula + caps |
| **State** | The verdict | `recommend` (bet it), `below filter` (edge too small), `opposite` (market disagrees with you) |
| **Passes filter** | Did it clear all the safety gates? | Only act on ones that pass |

**A worked example.** Suppose you see:
- Outcome: *3DMAX to beat TYLOO*
- Model prob: **0.58** (Betto thinks 3DMAX win 58% of the time)
- Market price: **0.50** (market is treating it as a coin flip)
- Edge: **+0.08** → an 8% advantage
- State: **recommend**, stake **2.0%** of bankroll

How to read it: *"The market is selling 3DMAX too cheaply. Over many bets like this, backing the 3DMAX side at 50¢ when it should be ~58¢ makes money. Betto suggests staking 2% of the bankroll — small, because no single bet should ever sink you."*

**Golden rules for using recommendations:**

1. **Never bet more than the suggested size.** The size *is* the risk control. Doubling it does not double your profit — it multiplies your risk of ruin.
2. **Trust the filter.** If `state` is *below filter* or it does not pass, skip it, even if it looks tempting.
3. **Think in seasons, not single bets.** Any one bet can lose. Edge only shows up across dozens or hundreds of bets. Judge Betto by the trend in the **Bet log** and **Strategies** screens, not by yesterday's result.
4. **Check the match time** (now shown in Romanian time on the Matches screen) so you bet *before* the game starts.
5. **Start on Paper.** Watch the paper Bet log turn green before you ever flip to Live.

To turn passing recommendations into (paper) bets:

```bash
.venv/bin/python -m core.cli.main db-log-paper-bets-from-recommendations --bankroll-usd 1000
```

Then watch them on the **Bet log** screen, and settle them once matches finish:

```bash
.venv/bin/python -m core.cli.main db-settle-paper-bets-from-market-fixtures
```

---

## 11. The exact state of YOUR system right now

A snapshot as of **2026-06-05**, so you know what is real and what is still to come.

**✅ Done and verified:**
- **HLTV match history**: ~4,388 matches, ~9,450 maps, ~94,000 player-map stat lines, ~2,820 teams/players.
- **Polymarket markets**: ~1,410 markets (open + closed).
- **Polymarket prices**: ~35,500 price snapshots.
- **Market → match links**: **8 markets** linked to their HLTV matches (all verified correct). These now appear at the top of the **Matches** screen with markets attached.
- **Match times** are shown in **Romanian time** throughout the Matches screen.
- The console, API and database are all running and correctly wired.

**⏳ Not done yet (and why your downstream screens are empty):**
- **Features, model, recommendations, backtests, paper bets = none yet.** Stations 3–7 of the assembly line ([section 6](#6-the-big-journey-how-raw-data-becomes-a-betting-tip)) have not been run. This is why **Today, Recommendations, Strategies, Backtests, Bet log** are quiet. Run sections 8–10 to fill them.
- **Bookmaker odds (oddspapi)**: not ingested, so **Edge compare** currently shows Polymarket prices only.
- **Live betting**: your Polymarket account credentials are **not configured**. Live mode and your real account history (`db-ingest-polymarket-account-history`) stay disabled until you add them. Paper mode works fully without them.

**👉 Suggested next steps, in order:**
1. Materialize features and run a walk-forward backtest ([section 8](#8-how-to-run-a-backtest)) to confirm the baseline strategy is sound.
2. Generate recommendations and log them as **paper** bets ([section 10](#10-how-to-read-and-use-recommendations)).
3. Watch them settle for a couple of weeks on the **Bet log** and **Strategies** screens.
4. Only then, add Polymarket credentials and consider Live mode.

---

## 12. Glossary

- **API** — the "kitchen": the program that serves data to the console. Lives at port 8000.
- **Backtest** — replaying history to test whether a strategy would have made money.
- **Bankroll** — the total pot of money you are betting with.
- **Brier score / log loss** — report-card scores for how accurate the model's probabilities are. **Lower is better.**
- **Console** — the website you look at. Lives at port 5173.
- **Contest / match** — one game between two teams (e.g. *3DMAX vs TYLOO*).
- **Database** — the "pantry": PostgreSQL, where all data is stored. Lives at port 5432.
- **Drawdown** — the size of a losing streak, measured from a peak to the following low point.
- **Edge** — your advantage: model probability minus market price. The whole point of Betto.
- **Feature** — a number describing history that the model learns from (e.g. a team's Mirage win-rate).
- **HLTV** — the website that publishes Counter-Strike match results; our source of history.
- **Idempotent** — safe to run more than once; repeats don't double-count.
- **Ingestion** — loading data into the database.
- **Kelly criterion** — the bet-sizing formula: bet more on big, confident edges, less on thin ones.
- **Kill switch** — an automatic emergency stop that halts betting if risk limits are breached.
- **Linking** — connecting a Polymarket market to the exact HLTV match it refers to.
- **Market** — a single thing you can bet on (e.g. "who wins 3DMAX vs TYLOO").
- **Model** — the program that turns features into a win probability.
- **Paper bet** — a pretend bet, for practice. No real money.
- **Polymarket** — the betting website where the markets and prices come from.
- **Port** — a numbered "door" on the server (5432 db, 8000 API, 5173 console).
- **Recommendation** — Betto's suggestion to bet a particular side, with a size and a reason.
- **Scraper** — the automated collector that fetches HLTV results every night.
- **Snapshot** — one recording of a market's price at one moment in time.
- **SSH tunnel** — the secure private connection that lets your laptop reach the server's locked doors.
- **Strategy** — the full rulebook: model + edge filter + bet sizing + safety gates.
- **Walk-forward** — the honest backtest method: only ever learn from the past, never peek at the future.

---

## 13. Cheat sheet & troubleshooting

**Open the console (from your laptop):**
```bash
ssh -L 5173:localhost:5173 -L 8000:localhost:8000 ubuntu@SERVER_ADDRESS
# then browse to http://localhost:5173
```

**Everyday commands (run on the server, from `/opt/betto/repo`):**
```bash
cd /opt/betto/repo

# Is the database alive?
.venv/bin/python -m core.cli.main db-check

# Load / refresh data
.venv/bin/python -m core.cli.main db-ingest-hltv-scraped --scraped-dir /opt/betto/scraper/data/hltv_scraped
.venv/bin/python -m core.cli.main db-ingest-polymarket-cs
.venv/bin/python -m core.cli.main db-ingest-polymarket-price-history

# Link markets to matches (preview first!)
.venv/bin/python -m core.cli.main db-link-polymarket-markets --dry-run
.venv/bin/python -m core.cli.main db-link-polymarket-markets

# Inspect what's in the database
.venv/bin/python -m core.cli.main db-list-recommendations --summary-only
.venv/bin/python -m core.cli.main db-list-backtest-runs
.venv/bin/python -m core.cli.main db-list-paper-bets
```

**"The console page won't load."** The dining room (console) or kitchen (API) isn't running. Start them on the server:
```bash
cd /opt/betto/repo
# Start the API (kitchen) on port 8000:
BETTO_API_DATA_SOURCE=postgres BETTO_API_PORT=8000 \
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5432/betto \
nohup .venv/bin/python scripts/dev_api_server.py > /tmp/betto-api.log 2>&1 &

# Start the console (dining room) on port 5173:
cd /opt/betto/repo/console
BETTO_API_URL=http://localhost:8000 nohup npm run dev > /tmp/betto-console.log 2>&1 &
```

**"A screen is empty."** First decide which kind of empty:
- *Matches / Edge compare empty* → a data or linking problem; re-run ingestion (section 7).
- *Today / Recommendations / Strategies / Backtests / Bet log empty* → the analytics pipeline hasn't been run yet; do sections 8–10. **This is the normal state of a fresh system.**

**"I want real-money betting."** You must first add your Polymarket account credentials to the server's settings (`BETTO_POLYMARKET_API_KEY`, `_SECRET`, `_PASSPHRASE`, `_PRIVATE_KEY`, `_ADDRESS`). Until then, Live mode and account-history import stay disabled by design. Ask before doing this — it involves real money.

**The most important habit:** stay on **Paper**, let the **Bet log** prove itself over many bets, and never override the recommended bet size. Discipline is the edge.
