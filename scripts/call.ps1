param(
    [string]$Scenario = "schedule_new",
    [string]$CallId = "01"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual env not found. Run setup first." -ForegroundColor Red
    exit 1
}

Write-Host "Placing call: scenario=$Scenario call-id=$CallId" -ForegroundColor Cyan
Write-Host "Watch the start.bat / server window for live logs." -ForegroundColor Yellow
Write-Host ""

& $venvPython "main.py" call --scenario $Scenario --call-id $CallId
