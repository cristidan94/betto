"""One-off maintenance: repair implausible best_of in scraped fixtures.

Earlier parser versions stored best_of as 0 (no fallback) or 1 (the old
"map_count if odd else 1" heuristic), which is provably wrong for any decided
series (a 2-0 sweep cannot be a Bo1). For each FINISHED fixture this raises
best_of to the floor the results prove -- 2 * max(map_wins) - 1 -- and never
lowers it, so single-map forfeits recorded as Bo3/Bo5 keep their value.

Offline (no network). Usage:
    python -m scripts.backfill_best_of            # dry run, report only
    python -m scripts.backfill_best_of --apply    # rewrite changed fixtures
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scraper.config import load_config
from scraper.parser import _results_floor


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    output_dir = Path(load_config().output_dir)
    changed: list[tuple[str, int, int]] = []
    skipped_scheduled = 0
    scanned = 0

    for path in sorted(output_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        scanned += 1
        if payload.get("status") != "finished":
            if int(payload.get("best_of") or 0) <= 0:
                skipped_scheduled += 1
            continue
        stored = int(payload.get("best_of") or 0)
        floor = _results_floor(payload.get("maps") or [])
        new_bo = max(stored, floor)
        if new_bo != stored:
            changed.append((str(payload.get("hltv_id") or path.stem), stored, new_bo))
            if args.apply:
                payload["best_of"] = new_bo
                raw = path.read_text(encoding="utf-8")
                out = json.dumps(payload, indent=2, sort_keys=True)
                if raw.endswith("\n"):
                    out += "\n"
                path.write_text(out, encoding="utf-8")

    print(json.dumps({
        "scanned": scanned,
        "changed": len(changed),
        "applied": args.apply,
        "skipped_unplayed_without_bestof": skipped_scheduled,
        "sample": [{"match_id": m, "from": a, "to": b} for m, a, b in changed[:15]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
