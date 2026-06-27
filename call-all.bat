@echo off
cd /d "%~dp0"
set STARTID=%~1
if "%STARTID%"=="" set STARTID=01
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\call-all.ps1" -StartId "%STARTID%"
