@echo off
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%supervisor.py"
set "TARGET_ENV=env_isaaclab"
set "CONDA_ROOT="
set "PY_EXE="
set "LISTEN_MODE="
set "FOREGROUND_MODE="
set "FORWARDED_ARGS="

for %%A in (%*) do (
    if /I "%%~A"=="--listen" set "LISTEN_MODE=1"
    if /I "%%~A"=="--foreground" set "FOREGROUND_MODE=1"
)

if defined LISTEN_MODE if not defined FOREGROUND_MODE (
    set "SPOT_MICRO_SUPERVISOR_BACKGROUND=1"
)

for %%A in (%*) do (
    if /I not "%%~A"=="--foreground" (
        set "FORWARDED_ARGS=!FORWARDED_ARGS! "
        set "FORWARDED_ARGS=!FORWARDED_ARGS!%%~A"
    )
)

for %%D in ("%USERPROFILE%\miniforge3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3") do (
    if not defined CONDA_ROOT if exist "%%~fD\Scripts\conda.exe" set "CONDA_ROOT=%%~fD"
)

if not defined CONDA_ROOT if defined CONDA_EXE (
    for %%D in ("%CONDA_EXE%") do set "CONDA_ROOT=%%~dpD.."
)

if defined CONDA_ROOT (
    if exist "%CONDA_ROOT%\envs\%TARGET_ENV%\python.exe" set "PY_EXE=%CONDA_ROOT%\envs\%TARGET_ENV%\python.exe"
    if exist "%CONDA_ROOT%\Scripts\conda.exe" set "CONDA_EXE=%CONDA_ROOT%\Scripts\conda.exe"
    if exist "%CONDA_ROOT%\Scripts\activate.bat" (
        set "CONDA_ACTIVATE_BAT=%CONDA_ROOT%\Scripts\activate.bat"
    ) else if exist "%CONDA_ROOT%\condabin\activate.bat" (
        set "CONDA_ACTIVATE_BAT=%CONDA_ROOT%\condabin\activate.bat"
    ) else if exist "%CONDA_ROOT%\condabin\conda.bat" (
        set "CONDA_ACTIVATE_BAT=%CONDA_ROOT%\condabin\conda.bat"
    )
)

if defined PY_EXE (
    "%PY_EXE%" "%SCRIPT_PATH%" %FORWARDED_ARGS%
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 "%SCRIPT_PATH%" %FORWARDED_ARGS%
    exit /b %ERRORLEVEL%
)

python "%SCRIPT_PATH%" %FORWARDED_ARGS%
exit /b %ERRORLEVEL%
