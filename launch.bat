@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

rem Headless Qt platform (e.g. from CI/tests) prevents any visible window.
set "QT_QPA_PLATFORM="
set "QT_QUICK_BACKEND="

if exist "%ROOT%scripts\run_meshstager.bat" (
  call "%ROOT%scripts\run_meshstager.bat"
  exit /b %ERRORLEVEL%
)

if exist "%ROOT%\.venv\Scripts\pythonw.exe" (
  "%ROOT%\.venv\Scripts\python.exe" -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    start "MeshStager" "%ROOT%\.venv\Scripts\pythonw.exe" -m meshcorral.app
    exit /b 0
  )
  echo MeshStager: .venv points to a missing Python — recreating is recommended.
)

where py >nul 2>&1
if not errorlevel 1 (
  start "MeshStager" py -3 -m meshcorral.app
  exit /b 0
)

if exist "%ROOT%\.venv\Scripts\python.exe" (
  start "MeshStager" "%ROOT%\.venv\Scripts\python.exe" -m meshcorral.app
  exit /b 0
)

echo MeshStager: no working Python found under %ROOT%
echo Create one: python -m venv .venv ^& .venv\Scripts\pip install -r requirements.txt
pause
exit /b 1
