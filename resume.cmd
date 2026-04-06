@echo off
setlocal

set "PROJECT_DIR=D:\project\spot_micro_rl"
set "LOG_DIR=%PROJECT_DIR%\logs\rsl_rl\spot_micro_flat"
set "RUN=2026-04-07_05-13-42"
set "CHECKPOINT=model_25500.pt"
set "NUM_ENVS=4096"
set "MAX_ITER=30000"
set "MODE=--headless"

if /i "%~1"=="gui" set "MODE=" & shift
if not "%~1"=="" set "RUN=%~1"
if not "%~2"=="" set "CHECKPOINT=%~2"
if not "%~3"=="" set "MAX_ITER=%~3"

set "FULL_PATH=%LOG_DIR%\%RUN%\%CHECKPOINT%"
if not exist "%FULL_PATH%" (
    echo ERROR: checkpoint not found: %FULL_PATH%
    exit /b 1
)

echo Resume: run=%RUN% checkpoint=%CHECKPOINT%
echo Mode: %MODE% envs=%NUM_ENVS% max_iter=%MAX_ITER%

call "C:\Users\etnlw\miniforge3\Scripts\activate.bat"
call conda activate env_isaaclab
set PYTHONDONTWRITEBYTECODE=1
cd /d "%PROJECT_DIR%"

"C:\IsaacLab\isaaclab.bat" -p scripts/rsl_rl/train.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=%NUM_ENVS% %MODE% --max_iterations=%MAX_ITER% --resume --load_run=%RUN% --checkpoint=%CHECKPOINT%
