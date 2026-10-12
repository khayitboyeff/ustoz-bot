@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment topilmadi. Avval quyidagilarni bajaring: py -m venv .venv
    exit /b 1
)

if not exist "logs" mkdir logs

powershell -NoProfile -Command "$bot = Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -match '(^|\s)bot\.py(\s|$)' }; if ($bot) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
    echo [INFO] Bot allaqachon ishlayapti.
    exit /b 0
)

if exist "bot.lock" del "bot.lock"
type nul > bot.lock
start "CyberLearn Uz Bot" /B ".venv\Scripts\python.exe" bot.py >> "logs\bot.log" 2>&1

if exist "bot.lock" (
    echo [INFO] Bot start command sent. Log fayli: logs\bot.log
)
