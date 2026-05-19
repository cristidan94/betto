param(
    [string]$ProjectPath = "",
    [string]$WslProjectPath = "",
    [string]$DatabaseUrl = "postgresql://betto:betto@localhost:5433/betto",
    [switch]$SkipMigrations,
    [switch]$NoShell
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

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if ([string]::IsNullOrWhiteSpace($WslProjectPath)) {
    $WslProjectPath = ConvertTo-WslPath $ProjectPath
}

$skipMigrationsValue = if ($SkipMigrations) { "1" } else { "0" }
$noShellValue = if ($NoShell) { "1" } else { "0" }

$escapedProject = $WslProjectPath.Replace("'", "'\''")
$escapedUrl = $DatabaseUrl.Replace("'", "'\''")
$command = "cd '$escapedProject' && BETTO_DATABASE_URL='$escapedUrl' BETTO_SKIP_MIGRATIONS='$skipMigrationsValue' BETTO_NO_SHELL='$noShellValue' bash scripts/wsl-start-betto.sh"

Write-Host "[betto] Starting WSL Betto environment at $WslProjectPath"
& wsl.exe bash -lc $command
