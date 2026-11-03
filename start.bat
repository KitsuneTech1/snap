@echo off
setlocal
echo ========================================================
echo   FocusSnap (snap)
echo   Kitsune Technologies LLC
echo ========================================================
echo.

if exist "%~dp0snap.exe" (
    "%~dp0snap.exe" --help
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0snap.ps1" -Help
)
pause
