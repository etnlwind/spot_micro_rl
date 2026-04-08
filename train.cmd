@echo off
setlocal

set "PROJECT_DIR=D:\project\spot_micro_rl"
set "NUM_ENVS=4096"
set "MAX_ITER=5000"
set "RUN_NAME=V62"
set "MODE=--headless"

if /i "%~1"=="gui" set "MODE=" & shift
if not "%~1"=="" set "MAX_ITER=%~1"

echo Train: envs=%NUM_ENVS% max_iter=%MAX_ITER%
echo Mode: %MODE%

call "C:\Users\etnlw\miniforge3\Scripts\activate.bat"
call conda activate env_isaaclab
set PYTHONDONTWRITEBYTECODE=1
cd /d "%PROJECT_DIR%"

"C:\IsaacLab\isaaclab.bat" -p scripts/rsl_rl/train.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=%NUM_ENVS% %MODE% --max_iterations=%MAX_ITER% --run_name=%RUN_NAME%
