@echo off

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%listener.py"
set "TARGET_ENV=env_isaaclab"
set "CONDA_ROOT="
set "PY_EXE="

rem WSL2 stale pyc 방지
set "PYTHONDONTWRITEBYTECODE=1"

for %%D in ("%USERPROFILE%\miniforge3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3") do (
    if not defined CONDA_ROOT if exist "%%~fD\Scripts\conda.exe" set "CONDA_ROOT=%%~fD"
)

if not defined CONDA_ROOT if defined CONDA_EXE (
    for %%D in ("%CONDA_EXE%") do set "CONDA_ROOT=%%~dpD.."
)

if defined CONDA_ROOT (
    if exist "%CONDA_ROOT%\envs\%TARGET_ENV%\python.exe" set "PY_EXE=%CONDA_ROOT%\envs\%TARGET_ENV%\python.exe"
)

if not defined PY_EXE (
    echo ERROR: python not found in conda env %TARGET_ENV%
    exit /b 1
)

set "LOG_FILE=%SCRIPT_DIR%log\listener.log"
set "PID_FILE=%SCRIPT_DIR%log\listener.pid"
if not exist "%SCRIPT_DIR%log" mkdir "%SCRIPT_DIR%log"

rem Check if previous listener is running
if not exist "%PID_FILE%" goto :start
set /p OLD_PID=<"%PID_FILE%"
if "%OLD_PID%"=="" goto :start
tasklist /FI "PID eq %OLD_PID%" /NH 2>nul | findstr /i "python" >nul
if errorlevel 1 goto :start

echo [WARN] Listener already running (PID %OLD_PID%)
set /p CONFIRM="Kill and restart? (Y/N): "
if /i "%CONFIRM%"=="Y" (
    taskkill /PID %OLD_PID% /F >nul 2>&1
    echo [OK] Killed PID %OLD_PID%
    ping -n 3 127.0.0.1 >nul
) else (
    echo [ABORT] Cancelled.
    exit /b 1
)

:start
start /b "" "%PY_EXE%" "%SCRIPT_PATH%" %* > "%LOG_FILE%" 2>&1
echo [OK] listener started in background (log: %LOG_FILE%)
exit /b 0
