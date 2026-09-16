@echo off
setlocal

cd /d "%~dp0\.."

echo Building MeshStager...
echo Spec: MeshStager.spec ^(entry run_frozen.py, equivalent to python -m meshcorral.app^)
echo.

rem MeshStager.spec is the canonical build input: it owns the entry point, icon, windowed
rem mode, onedir layout, and the SciPy hidden imports the native renderer needs. The
rem release build (scripts\build_shareable_windows.py) uses the same spec.

rem Prefer the repo venv: PyInstaller can only bundle what the build interpreter imports,
rem so a bare "python" on PATH without SciPy silently produces a crippled bundle.
set "PYI_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYI_PYTHON=.venv\Scripts\python.exe"
echo Build interpreter: %PYI_PYTHON%

"%PYI_PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  MeshStager.spec

if exist "README_FIRST.txt" copy /y "README_FIRST.txt" "dist\MeshStager\README_FIRST.txt" >nul

echo.
echo Build complete.
echo Output:
echo dist\MeshStager\MeshStager.exe
echo.
pause
