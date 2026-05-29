from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig, load_config
from scraper.health import collect_health
from scraper.quality import collect_quality_report
from scraper.status import collect_status
from scraper.validator import validate_fixtures


def write_html_report(path: Path, config: ScraperConfig | None = None) -> Path:
    if config is None:
        config = load_config()
    status = collect_status(config, recent_limit=10)
    quality = collect_quality_report(config, sample_limit=10)
    health = collect_health(config, recent_limit=25)
    validation = validate_fixtures(config, sample_limit=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(status, quality, health, validation), encoding="utf-8")
    return path


def _render(status: dict[str, Any], quality: dict[str, Any], health: dict[str, Any], validation: dict[str, Any]) -> str:
    queue = status["queue"]
    backfill = status["backfill"]
    coverage = quality["coverage"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HLTV Scraper Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #1f2933; background: #f7f8fa; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0 28px; }}
    .metric {{ background: white; border: 1px solid #dde2e7; border-radius: 6px; padding: 12px; }}
    .metric strong {{ display: block; font-size: 24px; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; background: white; margin-bottom: 28px; }}
    th, td {{ border: 1px solid #dde2e7; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f6; }}
    .ok {{ color: #146c43; }}
    .bad {{ color: #b42318; }}
    code {{ white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>HLTV Scraper Report</h1>
  <p>Health: <strong class="{_class(health["ok"])}">{html.escape(str(health["ok"]))}</strong> | Validation: <strong class="{_class(validation["ok"])}">{html.escape(str(validation["ok"]))}</strong> | Quality score: <strong>{quality["score"]}</strong></p>
  <h2>Queue</h2>
  <div class="grid">{_metrics(queue)}</div>
  <h2>Backfill</h2>
  <table>{_rows(backfill)}</table>
  <h2>Coverage</h2>
  <div class="grid">{_metrics(coverage)}</div>
  <h2>Health Checks</h2>
  <table>{_rows(health["checks"])}</table>
  <h2>Validation Errors</h2>
  <table>{_issue_rows(validation["errors"]["sample"])}</table>
  <h2>Quality Warnings</h2>
  <table>{_issue_rows(quality["warnings"]["sample"])}</table>
</body>
</html>
"""


def _metrics(values: dict[str, Any]) -> str:
    return "".join(f'<div class="metric">{html.escape(str(key))}<strong>{html.escape(str(value))}</strong></div>' for key, value in values.items())


def _rows(values: dict[str, Any]) -> str:
    rows = "".join(f"<tr><th>{html.escape(str(key))}</th><td><code>{html.escape(str(value))}</code></td></tr>" for key, value in values.items())
    return f"<tbody>{rows}</tbody>"


def _issue_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<tbody><tr><td>None</td></tr></tbody>"
    body = "".join(
        f"<tr><td>{html.escape(str(row.get('issue')))}</td><td>{html.escape(str(row.get('match_id', '')))}</td><td>{html.escape(str(row.get('file', '')))}</td><td><code>{html.escape(str(row))}</code></td></tr>"
        for row in rows
    )
    return f"<thead><tr><th>Issue</th><th>Match</th><th>File</th><th>Detail</th></tr></thead><tbody>{body}</tbody>"


def _class(ok: bool) -> str:
    return "ok" if ok else "bad"
