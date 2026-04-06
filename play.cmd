@echo off
setlocal

set "PROJECT_DIR=D:\project\spot_micro_rl"
set "LOG_DIR=%PROJECT_DIR%\logs\rsl_rl\spot_micro_flat"
set "RUN=2026-04-05_14-59-28"
set "CHECKPOINT=model_2600.pt"
set "NUM_ENVS=16"

if not "%~1"=="" set "RUN=%~1"
if not "%~2"=="" set "CHECKPOINT=%~2"
if not "%~3"=="" set "NUM_ENVS=%~3"

set "FULL_PATH=%LOG_DIR%\%RUN%\%CHECKPOINT%"
if not exist "%FULL_PATH%" (
    echo ERROR: checkpoint not found: %FULL_PATH%
    exit /b 1
)

echo Playing: run=%RUN% checkpoint=%CHECKPOINT% envs=%NUM_ENVS%

call "C:\Users\etnlw\miniforge3\Scripts\activate.bat"
call conda activate env_isaaclab
set PYTHONDONTWRITEBYTECODE=1
cd /d "%PROJECT_DIR%"

"C:\IsaacLab\isaaclab.bat" -p scripts/rsl_rl/play.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=%NUM_ENVS% --load_run=%RUN% --checkpoint=%CHECKPOINT%
