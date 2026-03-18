@echo off
setlocal EnableDelayedExpansion

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

"%PY_EXE%" "%SCRIPT_PATH%" %*
exit /b %ERRORLEVEL%
