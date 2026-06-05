@echo off
setlocal

cd /d "%~dp0\.."

echo Building shareable Windows portable ZIP...
echo Version: v0.1.0-rc3

.\.venv\Scripts\python.exe scripts\build_shareable_windows.py --version v0.1.0-rc3

echo.
echo Done.
pause

