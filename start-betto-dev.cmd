@echo off
setlocal

set "ROOT=%~dp0"

echo Starting Betto app...
echo This prepares WSL/Postgres, applies migrations, starts the API, starts the console, and opens the browser.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-betto-app.ps1"

endlocal
