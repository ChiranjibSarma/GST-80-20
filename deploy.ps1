<#
    Invoked by deploy.bat. Reuses the Windows installer in local SQLite mode,
    then serves the portal in this console and opens the browser when healthy.
    Does not register a service, alter the firewall, or replace an existing .env.
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $appDir 'install.ps1'
$server = Join-Path $appDir '.venv\Scripts\uvicorn.exe'
$url = "http://127.0.0.1:$Port"
Set-Location $appDir

if (-not (Test-Path $installer)) {
    Write-Error "Missing install.ps1 in $appDir"
    exit 1
}

# Do not mistake another already-running local service for this launch.
$socket = New-Object System.Net.Sockets.TcpClient
$portInUse = $false
try {
    $socket.Connect('127.0.0.1', $Port)
    $portInUse = $true
} catch {
    # A failed connection means nothing is listening on this local port.
} finally {
    $socket.Dispose()
}
if ($portInUse) {
    Write-Error "Port $Port is already in use. Try deploy.bat 8081 or stop the other service."
    exit 1
}

Write-Host "Setting up the portal (Python 3.11+ and internet, or wheelhouse/, required)..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -NoService -Sqlite -Port $Port
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not (Test-Path $server)) {
    Write-Error "The installer did not create $server"
    exit 1
}

Write-Host ""
Write-Host "Opening $url when the portal is ready. Keep this window open; Ctrl+C stops it."
$browserJob = Start-Job -ScriptBlock {
    param($address)
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $response = Invoke-WebRequest "$address/healthz" -UseBasicParsing -TimeoutSec 1
            if ($response.Content.Trim() -eq 'ok') {
                Start-Process $address
                return
            }
        } catch { }
    }
} -ArgumentList $url

try {
    & $server app.main:app --host 127.0.0.1 --port $Port
    $serverExit = $LASTEXITCODE
} finally {
    Stop-Job $browserJob -ErrorAction SilentlyContinue
    Remove-Job $browserJob -Force -ErrorAction SilentlyContinue
}
exit $serverExit
