@echo off
setlocal

set "PROJECT_DIR=D:\project\spot_micro_rl"
set "MODE=--headless"
set "RUN=2026-04-10_02-14-50_V63.I"
set "CHECKPOINT=model_4999.pt"
set "STEPS=1000"

if not "%~1"=="" set "RUN=%~1"
if not "%~2"=="" set "CHECKPOINT=%~2"
if not "%~3"=="" set "STEPS=%~3"

echo Record: Trajectory Mining from %RUN% / %CHECKPOINT%
echo Steps: %STEPS%

call "C:\Users\etnlw\miniforge3\Scripts\activate.bat"
call conda activate env_isaaclab
set PYTHONDONTWRITEBYTECODE=1
cd /d "%PROJECT_DIR%"

"C:\IsaacLab\isaaclab.bat" -p scripts/rsl_rl/record_trajectory.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=16 %MODE% --resume --load_run=%RUN% --checkpoint=%CHECKPOINT% --record_steps=%STEPS%
