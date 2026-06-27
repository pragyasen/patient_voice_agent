param(
    [string]$Scenario = "schedule_new",
    [string]$Text = "",
    [string]$Output = "voice-preview.wav"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual env not found. Run setup first." -ForegroundColor Red
    exit 1
}

$args = @("main.py", "preview-voice", "--scenario", $Scenario, "--output", $Output)
if ($Text) {
    $args += @("--text", $Text)
}

Write-Host "Generating local voice preview (no Twilio call)..." -ForegroundColor Cyan
& $venvPython @args
