param(
    [string]$ProjectPath = "",
    [string]$WslProjectPath = "",
    [string]$DatabaseUrl = "postgresql://betto:betto@localhost:5433/betto",
    [string]$BettoCommand = "python -m core.cli.main db-check",
    [switch]$ApplyMigrations,
    [switch]$AllowSudo
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

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if ([string]::IsNullOrWhiteSpace($WslProjectPath)) {
    $WslProjectPath = ConvertTo-WslPath $ProjectPath
}

$applyMigrationsValue = if ($ApplyMigrations) { "1" } else { "0" }
$allowSudoValue = if ($AllowSudo) { "1" } else { "0" }

$escapedProject = ConvertTo-BashSingleQuoted $WslProjectPath
$escapedUrl = ConvertTo-BashSingleQuoted $DatabaseUrl
$escapedCommand = ConvertTo-BashSingleQuoted $BettoCommand

$wslCommand = "cd $escapedProject && BETTO_DATABASE_URL=$escapedUrl BETTO_APPLY_MIGRATIONS='$applyMigrationsValue' BETTO_ALLOW_SUDO='$allowSudoValue' bash scripts/wsl-run-betto.sh $escapedCommand"

Write-Host "[betto] Running WSL command at $WslProjectPath"
& wsl.exe bash -lc $wslCommand
