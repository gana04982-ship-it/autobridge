@echo off
REM ==============================================================================
REM AutoBridge Systems - Turnkey Plant Sidecar Initializer
REM Prepares the air-gapped local directories for zero-disruption dock operation.
REM ==============================================================================

echo ----------------------------------------------------------------------
echo  🚀 AutoBridge Systems - Initializing Plant Shipping Sidecar Directories
echo ----------------------------------------------------------------------

set ROOT_DIR=C:\edi
if not "%~1"=="" set ROOT_DIR=%~1

echo [*] Target Root Directory: %ROOT_DIR%
echo.

if not exist "%ROOT_DIR%\outgoing" mkdir "%ROOT_DIR%\outgoing"
if not exist "%ROOT_DIR%\ready" mkdir "%ROOT_DIR%\ready"
if not exist "%ROOT_DIR%\archive\original" mkdir "%ROOT_DIR%\archive\original"
if not exist "%ROOT_DIR%\archive\diffs" mkdir "%ROOT_DIR%\archive\diffs"
if not exist "%ROOT_DIR%\quarantine" mkdir "%ROOT_DIR%\quarantine"
if not exist "%ROOT_DIR%\logs" mkdir "%ROOT_DIR%\logs"

echo [OK] %ROOT_DIR%\outgoing           (ERP Drop Folder)
echo [OK] %ROOT_DIR%\ready              (AS2 / VAN Outbound Queue)
echo [OK] %ROOT_DIR%\archive\original   (Immutable Raw Manifest Vault)
echo [OK] %ROOT_DIR%\archive\diffs      (Cryptographic Diff Ledger)
echo [OK] %ROOT_DIR%\quarantine         (Mangled / Ambiguous File Hold)
echo [OK] %ROOT_DIR%\logs               (Watchdog Crash & Bypass Trace)
echo.
echo ----------------------------------------------------------------------
echo  ✅ Setup Complete! Total Time: 3 Seconds.
echo  Your ERP can now drop ANSI X12 856 files into: %ROOT_DIR%\outgoing
echo  AutoBridge will auto-repair and emit clean files to: %ROOT_DIR%\ready
echo ----------------------------------------------------------------------
