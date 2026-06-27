param(
    [string]$StartId = "01",
    [int]$Delay = 10
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual env not found. Run setup first." -ForegroundColor Red
    exit 1
}

Write-Host "Batch run: all scenarios, starting at call-id $StartId" -ForegroundColor Cyan
Write-Host "Keep start.bat running in another terminal." -ForegroundColor Yellow
Write-Host ""

& $venvPython "main.py" call-all --start-id $StartId --delay $Delay
