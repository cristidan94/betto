param(
    [string]$ProjectPath = "",
    [string]$WslProjectPath = "",
    [string]$DatabaseUrl = "postgresql://betto:betto@localhost:5433/betto",
    [double]$BankrollUsd = 1000.0,
    [switch]$AllowSudo
)

$ErrorActionPreference = "Stop"

$runner = Join-Path $PSScriptRoot "run-betto-wsl.ps1"
$common = @{
    DatabaseUrl = $DatabaseUrl
}
if (-not [string]::IsNullOrWhiteSpace($ProjectPath)) {
    $common.ProjectPath = $ProjectPath
}
if (-not [string]::IsNullOrWhiteSpace($WslProjectPath)) {
    $common.WslProjectPath = $WslProjectPath
}
if ($AllowSudo) {
    $common.AllowSudo = $true
}

$commands = @(
    "python -m core.cli.main db-ingest-cs-fixture --path tests/fixtures/cs_match_001.json",
    "python -m core.cli.main db-materialize-cs-features --as-of 2026-05-21T00:00:00Z --fixtures tests/fixtures/cs_match_001.json",
    "python -m core.cli.main db-list-cs-features --limit 10",
    "python -m core.cli.main db-evaluate-cs-baseline --fixtures tests/fixtures/cs_match_001.json --write-artifact",
    "python -m core.cli.main db-list-model-artifacts --target cs.map_winner",
    "python -m core.cli.main db-walk-forward-cs-baseline --corpus tests/fixtures/corpus --start 2026-01-01 --end 2026-03-31 --train-days 30 --validate-days 20 --step-days 15",
    "python -m core.cli.main db-list-backtest-runs --strategy-id cs_baseline_fixture_v1",
    "python -m core.cli.main db-paper-evaluate-cs-baseline --corpus tests/fixtures/cs_match_001.json --markets tests/fixtures/cs_market_prices.json --compact",
    "python -m core.cli.main db-list-recommendations --passing-only --limit 10",
    "python -m core.cli.main db-log-paper-bets-from-recommendations --strategy-id cs_baseline_fixture_v1 --bankroll-usd $BankrollUsd",
    "python -m core.cli.main db-settle-paper-bets-from-market-fixtures --markets tests/fixtures/cs_market_prices.json --strategy-id cs_baseline_fixture_v1",
    "python -m core.cli.main db-list-paper-bets --strategy-id cs_baseline_fixture_v1",
    "python -m core.cli.main db-summarize-paper-bets --strategy-id cs_baseline_fixture_v1",
    "python -m core.cli.main db-summarize-paper-bets-by-day --strategy-id cs_baseline_fixture_v1 --limit 10",
    "python -m core.cli.main db-check-paper-bet-readiness --strategy-id cs_baseline_fixture_v1 --min-settled-bets 1 --min-roi 0 --min-hit-rate 0 --min-mean-clv 0 --min-pnl-usd 0 --max-drawdown-usd 1000",
    "python -m core.cli.main db-report-cs-baseline-strategy --corpus tests/fixtures/corpus --markets tests/fixtures/market_corpus --compact",
    "python -m core.cli.main db-list-report-artifacts --strategy-id cs_baseline_fixture_v1"
)

& $runner @common -ApplyMigrations -BettoCommand "python -m core.cli.main db-check"
if ($LASTEXITCODE -ne 0) {
    throw "WSL command failed with exit code ${LASTEXITCODE}: python -m core.cli.main db-check"
}

foreach ($command in $commands) {
    Write-Host ""
    Write-Host "[betto] verify: $command"
    & $runner @common -BettoCommand $command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed with exit code ${LASTEXITCODE}: $command"
    }
}
