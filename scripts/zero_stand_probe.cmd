@echo off
setlocal

set TASK=Isaac-Velocity-Flat-SpotMicro-v0
set NUM_ENVS=16
set STEPS=300
set LOG_FILE=logs/diagnostics/zero_probe_latest.log

if not "%~1"=="" (
  C:\IsaacLab\isaaclab.bat -p D:\project\spot_micro_rl\scripts\utils\zero_stand_probe.py %*
) else (
  C:\IsaacLab\isaaclab.bat -p D:\project\spot_micro_rl\scripts\utils\zero_stand_probe.py --task %TASK% --num_envs %NUM_ENVS% --steps %STEPS% --log_file D:\project\spot_micro_rl\%LOG_FILE%
)

endlocal
