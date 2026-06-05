@echo off
setlocal

cd /d "%~dp0\.."

echo Building MeshStager installer (Inno Setup)...
echo Payload: dist\MeshStager\
echo.

if not exist "dist\MeshStager\MeshStager.exe" (
    echo ERROR: dist\MeshStager\MeshStager.exe not found.
    echo Run scripts\build_exe.bat first.
    pause
    exit /b 1
)

REM Optional docs beside the frozen app (picked up by installer\MeshStager.iss via recursive Files)
if exist "README_FIRST.txt" copy /y "README_FIRST.txt" "dist\MeshStager\" >nul
if exist "RELEASE_NOTES_v0.1.md" copy /y "RELEASE_NOTES_v0.1.md" "dist\MeshStager\" >nul
if exist "QUICK_QA_CHECKLIST.md" copy /y "QUICK_QA_CHECKLIST.md" "dist\MeshStager\" >nul
if exist "TESTER_HANDOFF_RC1.md" copy /y "TESTER_HANDOFF_RC1.md" "dist\MeshStager\" >nul

if not exist "dist_installer" mkdir dist_installer

set "ISCC="
if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo ERROR: ISCC.exe not found.
    echo Install Inno Setup 6 ^(bundles Inno Setup Compiler^) from https://jrsoftware.org/isdl.php
    echo Or add ISCC.exe to PATH and rerun.
    pause
    exit /b 1
)

"%ISCC%" "installer\MeshStager.iss"
if errorlevel 1 (
    echo Installer build failed.
    pause
    exit /b 1
)

echo.
echo Installer complete:
echo dist_installer\MeshStager_Setup_v0.1.0-rc1.exe
echo.
pause
