# Start VBots LiveKit worker with .env loaded (use instead of bare "dev" on Windows)
Set-Location $PSScriptRoot
$env:LIVEKIT_AGENT_NAME = "vbots"
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $k = $matches[1].Trim()
            $v = $matches[2].Trim()
            Set-Item -Path "env:$k" -Value $v
        }
    }
}
Write-Host "LIVEKIT_AGENT_NAME=$env:LIVEKIT_AGENT_NAME"
Write-Host "LIVEKIT_URL=$env:LIVEKIT_URL"
& .\.venv\Scripts\python.exe worker\agent.py start
