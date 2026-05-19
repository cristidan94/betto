"""Fetch historical CS2 odds from OddsPapi and convert to Betto market fixtures.

Standalone CLI script that:
  1. Fetches all CS2 fixtures in a date range from OddsPapi
  2. For each fixture, fetches Pinnacle historical odds (match + map winners)
  3. Saves raw API responses to data/oddspapi_raw/
  4. Converts to Betto market fixture format and saves to data/oddspapi_markets/
  5. Prints a summary of matches found, odds fetched, files written

Usage:
  python -m scripts.fetch_oddspapi_cs2 \\
      --api-key YOUR_KEY \\
      --from-date 2025-01-01 \\
      --to-date 2025-01-31

  # Or use the environment variable:
  BETTO_ODDSPAPI_API_KEY=YOUR_KEY python -m scripts.fetch_oddspapi_cs2 \\
      --from-date 2025-01-01 \\
      --to-date 2025-01-31
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sports.cs.ingestion.oddspapi import (
    OddsPapiClient,
    batch_fetch_cs2_odds,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fetch-oddspapi-cs2",
        description="Fetch historical CS2 Pinnacle odds from OddsPapi and convert to Betto market fixtures.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="OddsPapi API key. Falls back to BETTO_ODDSPAPI_API_KEY env var.",
    )
    parser.add_argument(
        "--from-date",
        required=True,
        help="Start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--to-date",
        required=True,
        help="End date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Base output directory. Raw files go to <out-dir>/oddspapi_raw/, market files to <out-dir>/oddspapi_markets/. Defaults to data/.",
    )
    parser.add_argument(
        "--raw-dir",
        default=None,
        help="Override raw output directory (default: <out-dir>/oddspapi_raw/).",
    )
    parser.add_argument(
        "--market-dir",
        default=None,
        help="Override market fixture output directory (default: <out-dir>/oddspapi_markets/).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.2,
        help="Delay in seconds between API requests for rate limiting (default: 1.2).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be fetched without making API calls.",
    )

    args = parser.parse_args(argv)

    # Resolve API key
    api_key = args.api_key or os.environ.get("BETTO_ODDSPAPI_API_KEY", "")
    if not api_key:
        print(
            json.dumps(
                {
                    "error": "missing_api_key",
                    "detail": (
                        "OddsPapi API key is required. "
                        "Pass --api-key or set the BETTO_ODDSPAPI_API_KEY environment variable."
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    # Resolve output directories
    base_dir = Path(args.out_dir).resolve() if args.out_dir else PROJECT_ROOT / "data"
    raw_dir = Path(args.raw_dir).resolve() if args.raw_dir else base_dir / "oddspapi_raw"
    market_dir = Path(args.market_dir).resolve() if args.market_dir else base_dir / "oddspapi_markets"

    if args.dry_run:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "from_date": args.from_date,
                    "to_date": args.to_date,
                    "raw_dir": str(raw_dir),
                    "market_dir": str(market_dir),
                    "delay_sec": args.delay,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    # Build client and fetch
    try:
        client = OddsPapiClient(
            api_key=api_key,
            request_delay_sec=args.delay,
        )
    except ValueError as exc:
        print(json.dumps({"error": "client_init_failed", "detail": str(exc)}, indent=2, sort_keys=True))
        return 1

    try:
        summary = batch_fetch_cs2_odds(
            client=client,
            from_date=args.from_date,
            to_date=args.to_date,
            raw_out_dir=raw_dir,
            market_out_dir=market_dir,
        )
    except Exception as exc:
        print(json.dumps({"error": "fetch_failed", "detail": str(exc)}, indent=2, sort_keys=True))
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
