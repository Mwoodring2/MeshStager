@echo off
setlocal

rem Thin wrapper kept for muscle memory. The canonical installer build is
rem scripts\build_installer_windows.ps1, which verifies the frozen payload (including SciPy),
rem locates ISCC.exe, and writes release\MeshStager_v<version>_Setup.exe plus a SHA256 sidecar.
rem
rem Neither script builds the application. Run the portable build first:
rem   .venv\Scripts\python.exe scripts\build_shareable_windows.py --version v0.1.0-rc3

cd /d "%~dp0\.."

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\build_installer_windows.ps1" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo Installer build failed with exit code %RC%.
)

pause
exit /b %RC%
