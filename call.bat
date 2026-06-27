@echo off
cd /d "%~dp0"
set SCENARIO=%~1
set CALLID=%~2
if "%SCENARIO%"=="" set SCENARIO=schedule_new
if "%CALLID%"=="" set CALLID=01
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\call.ps1" -Scenario "%SCENARIO%" -CallId "%CALLID%"
