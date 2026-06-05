@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

if exist "%ROOT%scripts\build_exe.bat" (
  call "%ROOT%scripts\build_exe.bat"
  exit /b %ERRORLEVEL%
)

echo build.bat: scripts\build_exe.bat not found.
exit /b 1
