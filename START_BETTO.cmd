@echo off
setlocal

set "ROOT=%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-betto-app.ps1"

endlocal
