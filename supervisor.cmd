@echo off
call "%~dp0scripts\supervisor.cmd" %*
exit /b %ERRORLEVEL%
