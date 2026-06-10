@echo off
REM theme-rotation daily auto-run (ASCII only; called by Task Scheduler)
chcp 65001 >nul
cd /d "%~dp0"

if not exist "data" mkdir "data"

echo. >> "data\run.log"
echo ==== %DATE% %TIME% START ==== >> "data\run.log"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py run_daily.py >> "data\run.log" 2>&1
) else (
  python run_daily.py >> "data\run.log" 2>&1
)

echo ==== END exit=%ERRORLEVEL% ==== >> "data\run.log"
