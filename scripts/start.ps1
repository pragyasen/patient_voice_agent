$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

. (Join-Path $PSScriptRoot "dev_utils.ps1")

$ngrokExe = Resolve-NgrokPath
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual env not found. Run setup first:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    Write-Host ".env not found. Copy .env.example to .env and add your API keys." -ForegroundColor Red
    exit 1
}

if (-not (Test-NgrokRunning)) {
    Write-Host "Starting ngrok in a new window..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "& '$ngrokExe' http 8000"
    ) | Out-Null
    Start-Sleep -Seconds 2
} else {
    Write-Host "ngrok is already running - reusing existing tunnel." -ForegroundColor Green
}

Write-Host "Waiting for ngrok public URL..." -ForegroundColor Cyan
$publicUrl = Get-NgrokPublicUrl
Set-EnvWebhookUrl -ProjectRoot $ProjectRoot -PublicUrl $publicUrl

Write-Host ""
Write-Host "Public webhook URL: $publicUrl" -ForegroundColor Green
Write-Host "Health check:         $publicUrl/health" -ForegroundColor Green
Write-Host ""
Write-Host "Starting server (Ctrl+C to stop). Place calls from another terminal:" -ForegroundColor Cyan
Write-Host '  .\call.bat schedule_new 01' -ForegroundColor White
Write-Host ""

& $venvPython main.py serve
