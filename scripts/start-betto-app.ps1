param(
    [string]$ProjectPath = "",
    [string]$WslProjectPath = "",
    [string]$DatabaseUrl = "postgresql://betto:betto@localhost:5433/betto",
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5073,
    [switch]$SkipMigrations
)

$ErrorActionPreference = "Stop"

function ConvertTo-WslPath {
    param([string]$WindowsPath)

    $resolved = (Resolve-Path $WindowsPath).Path
    if ($resolved -match "^([A-Za-z]):\\(.*)$") {
        $drive = $matches[1].ToLowerInvariant()
        $rest = $matches[2] -replace "\\", "/"
        return "/mnt/$drive/$rest"
    }
    throw "Cannot convert path to WSL path: $resolved"
}

function ConvertTo-BashSingleQuoted {
    param([string]$Value)
    return "'" + $Value.Replace("'", "'\''") + "'"
}

function ConvertTo-PowerShellSingleQuoted {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if ([string]::IsNullOrWhiteSpace($WslProjectPath)) {
    $WslProjectPath = ConvertTo-WslPath $ProjectPath
}

$frontendUrl = "http://localhost:$FrontendPort"
$apiUrl = "http://localhost:$ApiPort"
$skipMigrationsValue = if ($SkipMigrations) { "1" } else { "0" }
$quotedWslProject = ConvertTo-BashSingleQuoted $WslProjectPath
$quotedDbUrl = ConvertTo-BashSingleQuoted $DatabaseUrl

Write-Host "[betto] Preparing WSL, Postgres, and migrations..."
$prepareCommand = "cd $quotedWslProject && BETTO_DATABASE_URL=$quotedDbUrl BETTO_SKIP_MIGRATIONS='$skipMigrationsValue' BETTO_NO_SHELL='1' bash scripts/wsl-start-betto.sh"
& wsl.exe bash -lc $prepareCommand
if ($LASTEXITCODE -ne 0) {
    throw "WSL preparation failed. If Postgres needs sudo, run scripts\start-betto-wsl.ps1 once in an interactive terminal."
}

Write-Host "[betto] Starting API at $apiUrl"
$apiCommand = "cd $quotedWslProject && source .betto/wsl-venv/bin/activate && export BETTO_DATABASE_URL=$quotedDbUrl BETTO_API_DATA_SOURCE='postgres' BETTO_API_PORT='$ApiPort' && python scripts/dev_api_server.py"
$apiPowerShellCommand = "& wsl.exe bash -lc $(ConvertTo-PowerShellSingleQuoted $apiCommand)"
Start-Process powershell -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    $apiPowerShellCommand
)

Start-Sleep -Seconds 2

Write-Host "[betto] Starting console at $frontendUrl"
Start-Process powershell -WindowStyle Normal -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "Set-Location -LiteralPath '$ProjectPath\console'; `$env:BETTO_API_URL='$apiUrl'; npm run dev -- --host localhost --port $FrontendPort"
)

Start-Sleep -Seconds 4
Start-Process $frontendUrl

Write-Host "[betto] Ready:"
Write-Host "  API:     $apiUrl"
Write-Host "  Console: $frontendUrl"
