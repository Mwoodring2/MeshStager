@echo off
setlocal

cd /d "%~dp0\.."

echo Building MeshStager...
echo Entry: run_frozen.py ^(equivalent to python -m meshcorral.app^)
echo.

rem PyInstaller's -m is for Windows manifest, not a Python module. Use run_frozen.py.
rem If Qt plugins are missing on a target PC, add: --collect-all PySide6 ^

rem Icon: assets/icons/MeshStager_icon.ico (multi-size, Explorer / taskbar / Alt+Tab).
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name MeshStager ^
  --icon assets\icons\MeshStager_icon.ico ^
  --paths . ^
  run_frozen.py

if exist "README_FIRST.txt" copy /y "README_FIRST.txt" "dist\MeshStager\README_FIRST.txt" >nul

echo.
echo Build complete.
echo Output:
echo dist\MeshStager\MeshStager.exe
echo.
pause
