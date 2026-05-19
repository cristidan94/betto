from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.http import JsonHttpClient
from core.ingestion import FetchResult


ODDSPAPI_BASE_URL = "https://api.oddspapi.io/v4"
ODDSPAPI_SOURCE = "oddspapi"

# OddsPapi sport and market IDs for CS2
CS2_SPORT_ID = 17
MARKET_MATCH_WINNER = 171
MARKET_MAP1_WINNER = 173
MARKET_MAP2_WINNER = 175
MARKET_MAP3_WINNER = 177

MAP_WINNER_MARKETS: dict[int, int] = {
    1: MARKET_MAP1_WINNER,
    2: MARKET_MAP2_WINNER,
    3: MARKET_MAP3_WINNER,
}

# Conservative rate limit: sleep between API requests.
DEFAULT_REQUEST_DELAY_SEC = 1.2


@dataclass(frozen=True)
class OddsPapiFixture:
    """A CS2 fixture (match) from the OddsPapi fixtures endpoint."""

    fixture_id: str
    home_team: str
    away_team: str
    home_team_id: str | None
    away_team_id: str | None
    start_time: datetime | None
    league: str | None
    status: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class OddsPapiOddsSnapshot:
    """A single bookmaker odds snapshot for one selection."""

    fixture_id: str
    market_id: int
    bookmaker: str
    selection_name: str
    selection_id: str | None
    odds: float
    timestamp: datetime | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class OddsPapiHistoricalOdds:
    """Historical odds for a fixture from the OddsPapi historical-odds endpoint."""

    fixture_id: str
    market_id: int
    snapshots: tuple[OddsPapiOddsSnapshot, ...]
    raw_payload: FetchResult


@dataclass(frozen=True)
class OddsPapiFixtureList:
    """Result of listing CS2 fixtures for a date range."""

    fixtures: tuple[OddsPapiFixture, ...]
    raw_payload: FetchResult


class OddsPapiClient:
    """Client for the OddsPapi historical odds API.

    Uses stdlib urllib via the shared JsonHttpClient, matching the pattern
    established by PolymarketClient.
    """

    source = ODDSPAPI_SOURCE

    def __init__(
        self,
        api_key: str,
        base_url: str = ODDSPAPI_BASE_URL,
        http: JsonHttpClient | None = None,
        request_delay_sec: float = DEFAULT_REQUEST_DELAY_SEC,
    ) -> None:
        if not api_key:
            raise ValueError(
                "OddsPapi API key is required. Set BETTO_ODDSPAPI_API_KEY or pass --api-key."
            )
        self.api_key = api_key
        self.base_url = base_url
        self.http = http or JsonHttpClient(timeout_sec=30)
        self.request_delay_sec = request_delay_sec

    def _throttle(self) -> None:
        """Sleep between requests to respect rate limits."""
        if self.request_delay_sec > 0:
            time.sleep(self.request_delay_sec)

    def list_cs2_fixtures(
        self, from_date: str, to_date: str
    ) -> OddsPapiFixtureList:
        """List CS2 fixtures for a date range.

        Args:
            from_date: Start date in YYYY-MM-DD format.
            to_date: End date in YYYY-MM-DD format.

        Returns:
            OddsPapiFixtureList with parsed fixtures and raw payload.
        """
        params = {
            "apiKey": self.api_key,
            "sportId": CS2_SPORT_ID,
            "from": from_date,
            "to": to_date,
        }
        response = self.http.get(self.base_url, "/fixtures", params=params)
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data", payload.get("fixtures", []))
        if not isinstance(rows, list):
            rows = []
        fixtures = tuple(
            parsed
            for row in rows
            if isinstance(row, dict)
            for parsed in [_parse_fixture(row)]
            if parsed is not None
        )
        raw = FetchResult(
            source=self.source,
            source_id=f"fixtures-cs2-{from_date}-{to_date}",
            url=response.url,
            content=response.body,
            content_type=response.headers.get("content-type", "application/json"),
            fetched_at=datetime.now(timezone.utc),
        )
        return OddsPapiFixtureList(fixtures=fixtures, raw_payload=raw)

    def fetch_historical_odds(
        self,
        fixture_id: str,
        market_id: int = MARKET_MATCH_WINNER,
        bookmakers: str = "pinnacle",
    ) -> OddsPapiHistoricalOdds:
        """Fetch historical odds for a fixture and market.

        Args:
            fixture_id: The OddsPapi fixture ID.
            market_id: The market type ID (default: 171 match winner).
            bookmakers: Comma-separated bookmaker filter (default: pinnacle).

        Returns:
            OddsPapiHistoricalOdds with parsed snapshots and raw payload.
        """
        self._throttle()
        params = {
            "apiKey": self.api_key,
            "fixtureId": fixture_id,
            "bookmakers": bookmakers,
            "marketId": market_id,
        }
        response = self.http.get(self.base_url, "/historical-odds", params=params)
        payload = response.json()
        snapshots = _parse_odds_snapshots(fixture_id, market_id, payload)
        raw = FetchResult(
            source=self.source,
            source_id=f"historical-odds-{fixture_id}-{market_id}",
            url=response.url,
            content=response.body,
            content_type=response.headers.get("content-type", "application/json"),
            fetched_at=datetime.now(timezone.utc),
        )
        return OddsPapiHistoricalOdds(
            fixture_id=fixture_id,
            market_id=market_id,
            snapshots=tuple(snapshots),
            raw_payload=raw,
        )

    def fetch_pinnacle_closing_line(
        self, fixture_id: str, market_id: int = MARKET_MATCH_WINNER
    ) -> list[OddsPapiOddsSnapshot]:
        """Fetch the Pinnacle closing line for a fixture/market.

        Returns the last chronological odds snapshot per selection from Pinnacle,
        which represents the closing line.
        """
        result = self.fetch_historical_odds(
            fixture_id=fixture_id, market_id=market_id, bookmakers="pinnacle"
        )
        return _extract_closing_line(result.snapshots)

    def fetch_all_pinnacle_odds(
        self, fixture_id: str
    ) -> dict[int, OddsPapiHistoricalOdds]:
        """Fetch Pinnacle historical odds for match winner and all map winners.

        Returns a dict keyed by market_id with full historical odds.
        """
        markets_to_fetch = [MARKET_MATCH_WINNER] + list(MAP_WINNER_MARKETS.values())
        results: dict[int, OddsPapiHistoricalOdds] = {}
        for market_id in markets_to_fetch:
            results[market_id] = self.fetch_historical_odds(
                fixture_id=fixture_id,
                market_id=market_id,
                bookmakers="pinnacle",
            )
        return results


def _parse_fixture(row: dict[str, Any]) -> OddsPapiFixture | None:
    """Parse a single fixture row from the OddsPapi fixtures response."""
    fixture_id = str(row.get("id") or row.get("fixtureId") or row.get("fixture_id") or "")
    if not fixture_id:
        return None

    home = row.get("home") or row.get("homeTeam") or {}
    away = row.get("away") or row.get("awayTeam") or {}
    if isinstance(home, str):
        home_team = home
        home_team_id = None
    elif isinstance(home, dict):
        home_team = str(home.get("name") or home.get("team") or "")
        home_team_id = str(home.get("id") or home.get("teamId") or "") or None
    else:
        home_team = str(home)
        home_team_id = None

    if isinstance(away, str):
        away_team = away
        away_team_id = None
    elif isinstance(away, dict):
        away_team = str(away.get("name") or away.get("team") or "")
        away_team_id = str(away.get("id") or away.get("teamId") or "") or None
    else:
        away_team = str(away)
        away_team_id = None

    start_raw = row.get("startTime") or row.get("start_time") or row.get("commence_time")
    start_time = _parse_optional_datetime(start_raw)

    league_raw = row.get("league") or row.get("competition") or row.get("tournament")
    league = None
    if isinstance(league_raw, dict):
        league = str(league_raw.get("name") or league_raw.get("title") or "")
    elif isinstance(league_raw, str):
        league = league_raw

    return OddsPapiFixture(
        fixture_id=fixture_id,
        home_team=home_team,
        away_team=away_team,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        start_time=start_time,
        league=league,
        status=str(row.get("status") or "") or None,
        raw=row,
    )


def _parse_odds_snapshots(
    fixture_id: str, market_id: int, payload: Any
) -> list[OddsPapiOddsSnapshot]:
    """Parse odds snapshots from the historical-odds response."""
    snapshots: list[OddsPapiOddsSnapshot] = []
    if isinstance(payload, dict):
        data = payload.get("data") or payload.get("odds") or payload.get("bookmakers") or []
    elif isinstance(payload, list):
        data = payload
    else:
        return snapshots

    if not isinstance(data, list):
        data = [data] if isinstance(data, dict) else []

    for entry in data:
        if not isinstance(entry, dict):
            continue
        bookmaker = str(entry.get("bookmaker") or entry.get("bookmakerName") or entry.get("name") or "unknown")
        markets = entry.get("markets") or entry.get("odds") or entry.get("selections") or []
        if isinstance(markets, dict):
            markets = [markets]
        if not isinstance(markets, list):
            # The entry itself might be the market data
            _parse_selections_from_entry(snapshots, fixture_id, market_id, bookmaker, entry)
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            _parse_selections_from_entry(snapshots, fixture_id, market_id, bookmaker, market)

    return snapshots


def _parse_selections_from_entry(
    snapshots: list[OddsPapiOddsSnapshot],
    fixture_id: str,
    market_id: int,
    bookmaker: str,
    entry: dict[str, Any],
) -> None:
    """Extract selection odds from a market/entry dict."""
    selections = entry.get("selections") or entry.get("outcomes") or entry.get("odds") or []
    if isinstance(selections, dict):
        selections = [selections]
    if not isinstance(selections, list):
        return

    timestamp = _parse_optional_datetime(
        entry.get("timestamp") or entry.get("updatedAt") or entry.get("lastUpdate")
    )

    for sel in selections:
        if not isinstance(sel, dict):
            continue
        name = str(sel.get("name") or sel.get("selection") or sel.get("outcome") or "")
        sel_id = str(sel.get("id") or sel.get("selectionId") or "") or None
        odds_raw = sel.get("odds") or sel.get("price") or sel.get("decimal")
        if odds_raw is None:
            continue
        try:
            odds = float(odds_raw)
        except (TypeError, ValueError):
            continue
        sel_timestamp = _parse_optional_datetime(
            sel.get("timestamp") or sel.get("updatedAt")
        ) or timestamp
        snapshots.append(
            OddsPapiOddsSnapshot(
                fixture_id=fixture_id,
                market_id=market_id,
                bookmaker=bookmaker,
                selection_name=name,
                selection_id=sel_id,
                odds=odds,
                timestamp=sel_timestamp,
                raw=sel,
            )
        )


def _extract_closing_line(
    snapshots: tuple[OddsPapiOddsSnapshot, ...] | list[OddsPapiOddsSnapshot],
) -> list[OddsPapiOddsSnapshot]:
    """Extract the closing line: last snapshot per selection name."""
    latest: dict[str, OddsPapiOddsSnapshot] = {}
    for snap in snapshots:
        key = snap.selection_name
        existing = latest.get(key)
        if existing is None:
            latest[key] = snap
        elif snap.timestamp is not None and (
            existing.timestamp is None or snap.timestamp >= existing.timestamp
        ):
            latest[key] = snap
    return list(latest.values())


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Conversion to Betto CsMarketPriceFixture format
# ---------------------------------------------------------------------------

def decimal_odds_to_implied_prob(odds: float) -> float:
    """Convert European decimal odds to implied probability.

    e.g. 2.10 -> 1/2.10 = 0.4762
    """
    if odds <= 0:
        return 0.0
    return 1.0 / odds


def implied_probs_to_bid_ask(prob: float, vig_spread: float = 0.02) -> tuple[float, float]:
    """Convert an implied probability to a synthetic bid/ask pair.

    Pinnacle's closing odds already contain a small overround. We model the
    bid/ask spread symmetrically around the devigged probability.

    Args:
        prob: Implied probability from decimal odds.
        vig_spread: Total bid-ask spread width (default 0.02 = 2 cents).

    Returns:
        (best_bid, best_ask) tuple with bid < ask.
    """
    half = vig_spread / 2.0
    bid = max(0.01, round(prob - half, 4))
    ask = min(0.99, round(prob + half, 4))
    return bid, ask


def convert_closing_line_to_market_fixtures(
    fixture: OddsPapiFixture,
    closing_odds: list[OddsPapiOddsSnapshot],
    market_id: int,
    contest_hltv_id: str | None = None,
    team_hltv_ids: dict[str, str] | None = None,
    vig_spread: float = 0.02,
) -> list[dict[str, Any]]:
    """Convert Pinnacle closing line odds into Betto CsMarketPriceFixture dicts.

    Args:
        fixture: The OddsPapiFixture for context.
        closing_odds: Closing line snapshots (from _extract_closing_line).
        market_id: Which OddsPapi market these odds are for.
        contest_hltv_id: Override contest ID. Defaults to fixture_id.
        team_hltv_ids: Mapping from selection name to HLTV team ID.
        vig_spread: Synthetic bid/ask spread width.

    Returns:
        List of dicts matching CsMarketPriceFixture JSON schema.
    """
    if contest_hltv_id is None:
        contest_hltv_id = fixture.fixture_id

    # Determine map_index from market_id
    map_index = 0  # 0 = match winner
    for idx, mid in MAP_WINNER_MARKETS.items():
        if mid == market_id:
            map_index = idx
            break

    # Build team_hltv_ids mapping if not provided
    if team_hltv_ids is None:
        team_hltv_ids = _infer_team_ids(fixture, closing_odds)

    # Calculate devigged probabilities
    raw_probs = {}
    for snap in closing_odds:
        raw_probs[snap.selection_name] = decimal_odds_to_implied_prob(snap.odds)

    # Remove vig: normalize probabilities to sum to 1
    total_prob = sum(raw_probs.values())
    devigged: dict[str, float] = {}
    if total_prob > 0:
        for name, prob in raw_probs.items():
            devigged[name] = prob / total_prob
    else:
        devigged = raw_probs

    results: list[dict[str, Any]] = []
    for snap in closing_odds:
        team_id = team_hltv_ids.get(snap.selection_name, snap.selection_name)
        prob = devigged.get(snap.selection_name, 0.5)
        bid, ask = implied_probs_to_bid_ask(prob, vig_spread)

        taken_at = snap.timestamp or fixture.start_time or datetime.now(timezone.utc)

        entry: dict[str, Any] = {
            "contest_hltv_id": contest_hltv_id,
            "map_index": map_index,
            "team_hltv_id": team_id,
            "best_bid": bid,
            "best_ask": ask,
            "taken_at": taken_at.isoformat().replace("+00:00", "Z") if taken_at.tzinfo else taken_at.isoformat() + "Z",
        }

        # Include close_price as the devigged probability
        entry["close_price"] = round(prob, 4)

        results.append(entry)

    return results


def _infer_team_ids(
    fixture: OddsPapiFixture,
    odds: list[OddsPapiOddsSnapshot],
) -> dict[str, str]:
    """Best-effort mapping from selection name to a team ID.

    Uses the OddsPapi fixture home/away IDs when available, falling back to
    the selection name as a sanitized identifier.
    """
    mapping: dict[str, str] = {}
    home_name = fixture.home_team.strip().lower()
    away_name = fixture.away_team.strip().lower()

    for snap in odds:
        sel = snap.selection_name.strip().lower()
        if sel == home_name or _fuzzy_team_match(sel, home_name):
            mapping[snap.selection_name] = fixture.home_team_id or fixture.home_team
        elif sel == away_name or _fuzzy_team_match(sel, away_name):
            mapping[snap.selection_name] = fixture.away_team_id or fixture.away_team
        else:
            mapping[snap.selection_name] = snap.selection_id or snap.selection_name

    return mapping


def _fuzzy_team_match(sel: str, team: str) -> bool:
    """Simple substring-based fuzzy match for team names."""
    return sel in team or team in sel


def batch_fetch_cs2_odds(
    client: OddsPapiClient,
    from_date: str,
    to_date: str,
    raw_out_dir: Path | None = None,
    market_out_dir: Path | None = None,
    team_hltv_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Batch-fetch a date range of CS2 matches with Pinnacle odds.

    Args:
        client: Configured OddsPapiClient.
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).
        raw_out_dir: Directory to save raw API responses (optional).
        market_out_dir: Directory to save converted market fixtures (optional).
        team_hltv_ids: Optional global team ID mapping.

    Returns:
        Summary dict with counts of fixtures, odds fetched, and files written.
    """
    # Fetch fixtures
    fixture_list = client.list_cs2_fixtures(from_date, to_date)

    raw_files_written: list[str] = []
    market_files_written: list[str] = []
    odds_fetched = 0
    errors: list[dict[str, str]] = []

    # Save raw fixtures response
    if raw_out_dir is not None:
        raw_out_dir.mkdir(parents=True, exist_ok=True)
        fixtures_raw_path = raw_out_dir / f"fixtures_{from_date}_{to_date}.json"
        fixtures_raw_path.write_bytes(fixture_list.raw_payload.content)
        raw_files_written.append(str(fixtures_raw_path))

    all_market_entries: list[dict[str, Any]] = []

    for fixture in fixture_list.fixtures:
        # Fetch all Pinnacle odds for this fixture
        try:
            all_odds = client.fetch_all_pinnacle_odds(fixture.fixture_id)
        except Exception as exc:
            errors.append({
                "fixture_id": fixture.fixture_id,
                "error": str(exc),
            })
            continue

        for market_id, historical in all_odds.items():
            odds_fetched += len(historical.snapshots)

            # Save raw response
            if raw_out_dir is not None:
                raw_path = raw_out_dir / f"odds_{fixture.fixture_id}_{market_id}.json"
                raw_path.write_bytes(historical.raw_payload.content)
                raw_files_written.append(str(raw_path))

            # Convert closing line to market fixtures
            closing = _extract_closing_line(historical.snapshots)
            if closing:
                entries = convert_closing_line_to_market_fixtures(
                    fixture=fixture,
                    closing_odds=closing,
                    market_id=market_id,
                    team_hltv_ids=team_hltv_ids,
                )
                all_market_entries.extend(entries)

    # Save market fixtures
    if market_out_dir is not None and all_market_entries:
        market_out_dir.mkdir(parents=True, exist_ok=True)
        market_path = market_out_dir / f"oddspapi_cs2_{from_date}_{to_date}.json"
        market_path.write_text(
            json.dumps(all_market_entries, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        market_files_written.append(str(market_path))

    return {
        "from_date": from_date,
        "to_date": to_date,
        "fixtures_found": len(fixture_list.fixtures),
        "odds_snapshots_fetched": odds_fetched,
        "market_entries_converted": len(all_market_entries),
        "raw_files_written": len(raw_files_written),
        "market_files_written": len(market_files_written),
        "raw_file_paths": raw_files_written,
        "market_file_paths": market_files_written,
        "errors": errors,
    }


def convert_raw_oddspapi_to_market_fixtures(
    raw_dir: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """Convert already-downloaded raw OddsPapi JSON files to market fixtures.

    Reads all raw JSON files from raw_dir, parses fixtures and odds, and writes
    converted market fixtures to out_dir.

    Args:
        raw_dir: Directory containing raw OddsPapi JSON files.
        out_dir: Directory to write converted market fixture JSON files.

    Returns:
        Summary dict with conversion counts.
    """
    if not raw_dir.is_dir():
        raise ValueError(f"Raw directory does not exist: {raw_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Read fixture files to build fixture context
    fixtures_by_id: dict[str, OddsPapiFixture] = {}
    fixture_files = sorted(raw_dir.glob("fixtures_*.json"))
    for fpath in fixture_files:
        try:
            payload = json.loads(fpath.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else payload.get("data", payload.get("fixtures", []))
            if not isinstance(rows, list):
                rows = []
            for row in rows:
                if isinstance(row, dict):
                    parsed = _parse_fixture(row)
                    if parsed is not None:
                        fixtures_by_id[parsed.fixture_id] = parsed
        except (json.JSONDecodeError, OSError):
            continue

    # Read odds files and convert
    all_entries: list[dict[str, Any]] = []
    odds_files_processed = 0

    odds_files = sorted(raw_dir.glob("odds_*.json"))
    for opath in odds_files:
        parts = opath.stem.split("_")
        # Expected filename: odds_{fixture_id}_{market_id}.json
        if len(parts) < 3:
            continue
        fixture_id = parts[1]
        try:
            market_id = int(parts[2])
        except ValueError:
            continue

        try:
            payload = json.loads(opath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        snapshots = _parse_odds_snapshots(fixture_id, market_id, payload)
        closing = _extract_closing_line(snapshots)
        if not closing:
            continue

        odds_files_processed += 1

        fixture = fixtures_by_id.get(fixture_id)
        if fixture is None:
            # Create a minimal fixture stub
            fixture = OddsPapiFixture(
                fixture_id=fixture_id,
                home_team="",
                away_team="",
                home_team_id=None,
                away_team_id=None,
                start_time=None,
                league=None,
                status=None,
                raw={},
            )

        entries = convert_closing_line_to_market_fixtures(
            fixture=fixture,
            closing_odds=closing,
            market_id=market_id,
        )
        all_entries.extend(entries)

    # Write output
    market_files_written: list[str] = []
    if all_entries:
        out_path = out_dir / "oddspapi_cs2_converted.json"
        out_path.write_text(
            json.dumps(all_entries, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        market_files_written.append(str(out_path))

    return {
        "fixture_files_found": len(fixture_files),
        "fixtures_parsed": len(fixtures_by_id),
        "odds_files_found": len(odds_files),
        "odds_files_processed": odds_files_processed,
        "market_entries_converted": len(all_entries),
        "market_files_written": len(market_files_written),
        "market_file_paths": market_files_written,
    }
