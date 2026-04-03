@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

pushd "%REPO_ROOT%" >nul

set "ISAACLAB_BAT=C:\IsaacLab\isaaclab.bat"
if not exist "%ISAACLAB_BAT%" (
    echo ERROR: IsaacLab launcher not found at %ISAACLAB_BAT%
    popd >nul
    exit /b 1
)

set "DEFAULT_TASK=Isaac-Velocity-Flat-SpotMicro-v0"
set "DEFAULT_LOG=logs/diagnostics/standing_actuator_search_latest.log"
set "DEFAULT_JSON=logs/diagnostics/standing_actuator_search_latest.json"

if "%~1"=="" (
    echo [INFO] Running standing actuator search...
    echo [INFO] task=%DEFAULT_TASK%
    echo [INFO] log=%DEFAULT_LOG%
    call "%ISAACLAB_BAT%" -p scripts/utils/standing_actuator_search.py --task %DEFAULT_TASK% --steps 120 --headless --log_file %DEFAULT_LOG% --checkpoint_file %DEFAULT_JSON%
) else (
    call "%ISAACLAB_BAT%" -p scripts/utils/standing_actuator_search.py %*
)

set "EXIT_CODE=%ERRORLEVEL%"
popd >nul
exit /b %EXIT_CODE%
