@echo off
cd /d "%~dp0"
set SCENARIO=%~1
if "%SCENARIO%"=="" set SCENARIO=schedule_new
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\preview.ps1" -Scenario "%SCENARIO%"
