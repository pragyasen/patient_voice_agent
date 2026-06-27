function Resolve-NgrokPath {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
        [System.Environment]::GetEnvironmentVariable("Path", "User")

    $cmd = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $wingetPath = Join-Path $env:LOCALAPPDATA `
        "Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
    if (Test-Path $wingetPath) {
        return $wingetPath
    }

    throw "ngrok not found. Install with: winget install Ngrok.Ngrok"
}

function Get-NgrokPublicUrl {
    param([int]$TimeoutSeconds = 20)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
            $httpsTunnel = $response.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
            if ($httpsTunnel.public_url) {
                return $httpsTunnel.public_url.TrimEnd("/")
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    throw "Could not read ngrok public URL. Is ngrok running on port 8000?"
}

function Set-EnvWebhookUrl {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$PublicUrl
    )

    $envFile = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envFile)) {
        throw ".env not found. Copy .env.example to .env and fill in your API keys."
    }

    $content = Get-Content $envFile -Raw
    if ($content -match "(?m)^PUBLIC_WEBHOOK_URL=.*$") {
        $content = [regex]::Replace(
            $content,
            "(?m)^PUBLIC_WEBHOOK_URL=.*$",
            "PUBLIC_WEBHOOK_URL=$PublicUrl"
        )
    } else {
        $content = $content.TrimEnd() + "`nPUBLIC_WEBHOOK_URL=$PublicUrl`n"
    }

    Set-Content -Path $envFile -Value $content -NoNewline
}

function Test-NgrokRunning {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}
