@echo off
REM ==============================================================================
REM AutoBridge Systems - 1-Click Dock Station Launcher
REM Boots the local embedded HTTP server, folder-watcher sidecar, and UI dashboard.
REM ==============================================================================

set PYTHONPATH=%~dp0
set PORT=8080
if not "%~1"=="" set PORT=%~1

echo ==============================================================================
echo   🚀 STARTING AUTOBRIDGE LOCAL AIR-GAPPED DOCK FIREWALL
echo ==============================================================================
echo   * Host UI Interface : http://localhost:%PORT%
echo   * Watched Incoming  : C:\edi\outgoing
echo   * Ready Outgoing    : C:\edi\ready
echo   * Air-Gapped Mode   : ACTIVE (Zero external network sockets)
echo ==============================================================================
echo.

REM Launch Web Server in Background
start "AutoBridge Web Server" /B python -m autobridge.server %PORT%

REM Launch Watcher Daemon in Background
start "AutoBridge Watcher Daemon" /B python -m autobridge.cli watch --in C:\edi\outgoing --out C:\edi\ready --archive C:\edi\archive --quarantine C:\edi\quarantine

REM Wait 1 second and open default browser
timeout /t 1 /nobreak >nul
start http://localhost:%PORT%

echo [OK] AutoBridge is now running on your dock.
echo Keep this window open or minimize to system tray.
echo Press Ctrl+C to terminate.
echo.
pause
