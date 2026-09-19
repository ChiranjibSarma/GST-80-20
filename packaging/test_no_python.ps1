[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Exe, [Parameter(Mandatory=$true)][string]$DataDir,
      [string]$Fixtures = '', [int]$Port = 19080, [switch]$OccupyPort)
$ErrorActionPreference = 'Stop'
$Exe = (Resolve-Path -LiteralPath $Exe).Path
$DataDir = [IO.Path]::GetFullPath($DataDir)
if (Test-Path -LiteralPath $DataDir) { throw 'Use a NEW empty test data directory. No client data may be overwritten.' }
New-Item -ItemType Directory -Path "$DataDir\var" -Force | Out-Null
if ($Fixtures) {
    Copy-Item -LiteralPath "$Fixtures\installation-id","$Fixtures\license.json" -Destination "$DataDir\var"
}
$savedPath = $env:PATH
$savedPythonPath = $env:PYTHONPATH
$process = $null
$listener = $null
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYTHONPATH = ''
    if (Get-Command python.exe,py.exe,pip.exe -ErrorAction SilentlyContinue) { throw 'Python/pip unexpectedly visible in isolated PATH.' }
    foreach ($name in @('DATABASE_URL','VAR_DIR','GST8020_DATA_DIR','UPLOAD_DIR','BACKUP_DIR','SECRET_KEY','BOOTSTRAP_ADMIN_EMAIL','BOOTSTRAP_ADMIN_PASSWORD')) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    $installDir = "$DataDir\program"
    $sentinel = "$DataDir\var\preserve.txt"
    'existing-data-must-be-preserved' | Set-Content $sentinel
    for ($installation=0; $installation -lt 2; $installation++) {
        $setup = Start-Process -FilePath $Exe -ArgumentList @('--install-only','--install-dir',('"'+$installDir+'"'),'--no-shortcut') -WindowStyle Hidden -PassThru -Wait
        if ($setup.ExitCode -ne 0) { throw 'Isolated payload installation/upgrade failed.' }
        if ((Get-Content $sentinel -Raw).Trim() -ne 'existing-data-must-be-preserved') { throw 'Installation overwrote existing data.' }
    }
    $installedExe = "$installDir\GST-80-20.exe"
    if ((Get-FileHash $Exe).Hash -ne (Get-FileHash $installedExe).Hash) { throw 'Installed EXE differs from package.' }
    $gui = Start-Process -FilePath $installedExe -ArgumentList '--check-gui' -WindowStyle Hidden -PassThru -Wait
    if ($gui.ExitCode -ne 0) { throw 'Bundled Tk GUI runtime failed.' }
    if ($OccupyPort) {
        $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$Port)
        $listener.Start()
    }
    $process = Start-Process -FilePath $installedExe -ArgumentList @('--serve','--no-browser','--data-dir',('"'+$DataDir+'"'),'--port',$Port) -WindowStyle Hidden -PassThru
    $statusFile = "$DataDir\var\launcher-status.json"
    for ($attempt=0; $attempt -lt 120; $attempt++) {
        if ($process.HasExited) { throw "EXE exited before readiness. Review $DataDir\var\launcher.log" }
        if (Test-Path -LiteralPath $statusFile) {
            $status = Get-Content -LiteralPath $statusFile -Raw | ConvertFrom-Json
            try { if ((Invoke-WebRequest "$($status.url)/healthz" -UseBasicParsing).Content.Trim() -eq 'ok') { break } } catch { }
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $status -or -not $status.frozen) { throw 'Frozen server did not become ready.' }
    if ($OccupyPort -and $status.url -eq "http://127.0.0.1:$Port") { throw 'Launcher did not skip the occupied port.' }
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $page = Invoke-WebRequest "$($status.url)/login" -WebSession $session -UseBasicParsing
    $csrf = [Net.WebUtility]::HtmlDecode([regex]::Match($page.Content, 'name="csrf_token_value" value="([^"]+)"').Groups[1].Value)
    if (-not $csrf) { throw 'Login template/CSRF is missing.' }
    $login = Invoke-WebRequest "$($status.url)/login" -Method Post -WebSession $session -UseBasicParsing -Body @{
        email='admin@oswalgroup.net';password='admin123456789';csrf_token_value=$csrf
    }
    $form = Invoke-WebRequest "$($status.url)/gst8020/new" -WebSession $session -UseBasicParsing
    if ($form.Content -notmatch 'Day Book Register') { throw 'Application form/assets did not render.' }
    foreach ($name in @('Day_Book_Register_Template.xlsx','Search_Voucher_Template.xlsx','Creditors_Details_Template.xlsx')) {
        $template = Invoke-WebRequest "$($status.url)/static/input-templates/$name" -WebSession $session -UseBasicParsing
        if ($template.StatusCode -ne 200) { throw 'Bundled input template is missing.' }
    }
    if ($Fixtures) {
        function Upload-Month([string]$month) {
            $boundary = 'GSTQA' + [guid]::NewGuid().ToString('N')
            $stream = New-Object IO.MemoryStream
            function Append-Text([string]$value) { $bytes=[Text.Encoding]::UTF8.GetBytes($value); $stream.Write($bytes,0,$bytes.Length) }
            Append-Text "--$boundary`r`nContent-Disposition: form-data; name=`"csrf_token_value`"`r`n`r`n$csrf`r`n"
            foreach ($field in @('daybook','voucher','creditors')) {
                $name = if ($field -eq 'creditors') { 'creditors.xlsx' } else { "$month-$field.xlsx" }
                Append-Text "--$boundary`r`nContent-Disposition: form-data; name=`"$field`"; filename=`"$name`"`r`nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`r`n`r`n"
                $bytes = [IO.File]::ReadAllBytes((Join-Path $Fixtures $name)); $stream.Write($bytes,0,$bytes.Length)
                Append-Text "`r`n"
            }
            Append-Text "--$boundary--`r`n"
            try { Invoke-WebRequest "$($status.url)/gst8020/new" -Method Post -WebSession $session -UseBasicParsing -ContentType "multipart/form-data; boundary=$boundary" -Body $stream.ToArray() }
            finally { $stream.Dispose() }
        }
        $july = Upload-Month 'july'
        $id = [regex]::Match($july.BaseResponse.ResponseUri.AbsolutePath, '/runs/(\d+)').Groups[1].Value
        if (-not $id) { throw 'July upload did not save.' }
        Invoke-WebRequest "$($status.url)/gst8020/runs/$id/freeze" -Method Post -WebSession $session -UseBasicParsing -Body @{csrf_token_value=$csrf} | Out-Null
        try { Upload-Month 'july' | Out-Null; throw 'Frozen July replacement unexpectedly succeeded.' }
        catch { if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 409) { throw } }
        $august = Upload-Month 'august'
        $id = [regex]::Match($august.BaseResponse.ResponseUri.AbsolutePath, '/runs/(\d+)').Groups[1].Value
        if (-not $id -or $august.Content -notmatch 'Aug-26') { throw 'August was not saved as Aug-26.' }
        Invoke-WebRequest "$($status.url)/gst8020/runs/$id/export.xlsx" -WebSession $session -UseBasicParsing -OutFile "$DataDir\august-export.xlsx" | Out-Null
        if (@(Get-ChildItem "$DataDir\var\backups\*.sqlite3").Count -ne 2) { throw 'Two calculation-save backups were not produced.' }
    } else {
        try { Invoke-WebRequest "$($status.url)/gst8020/new" -Method Post -WebSession $session -UseBasicParsing -Body @{csrf_token_value=$csrf} | Out-Null; throw 'Missing-licence write unexpectedly succeeded.' }
        catch { if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 423) { throw } }
    }
    Write-Host "PASS: install/upgrade preserve data; bundled GUI/server/login/templates work without Python/pip in PATH. Fixtures supplied: $([bool]$Fixtures)."
    @{result='PASS';url=$status.url;frozen=$status.frozen;pythonVisible=$false;licensedWorkflow=[bool]$Fixtures;installUpgradePreservedData=$true;guiRuntime=$true;occupiedPortSkipped=[bool]$OccupyPort} | ConvertTo-Json | Set-Content "$DataDir\test-result.json"
} finally {
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    # Stop only this test's child by its recorded PID, never the live portal.
    if ($status -and $status.pid) { Stop-Process -Id $status.pid -Force -ErrorAction SilentlyContinue }
    if ($listener) { $listener.Stop() }
    $env:PATH = $savedPath
    $env:PYTHONPATH = $savedPythonPath
}
