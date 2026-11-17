param([ValidateRange(1024,65535)][int]$Port = 8778, [switch]$OpenBrowser, [switch]$LocalModel)
$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'Run scripts\setup.ps1 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot '.env'))) { throw 'Create .env from .env.example and configure your model API.' }
$RuntimePath = Join-Path $ProjectRoot 'runtime'
# A second process would share SQLite and mark running tasks interrupted.
# Check process ownership before touching PID files, logs or the database.
$OwnedServers = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.ExecutablePath -eq $ProjectPython -and $_.CommandLine -match '(?:^|\s)-m\s+uvicorn\s+app\.main:app(?:\s|$)'
})
if ($OwnedServers.Count -gt 1) { throw 'Multiple servers already use this project. Resolve them before starting another.' }
if ($OwnedServers.Count -eq 1) {
    $Existing = $OwnedServers[0]
    $ExistingPort = if ($Existing.CommandLine -match '--port(?:=|\s+)(\d+)') { [int]$Matches[1] } else { 8000 }
    if ($ExistingPort -ne $Port) {
        throw "This project is already running on port $ExistingPort. Wait for research to finish, stop it, then change ports."
    }
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        $Status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/status" -TimeoutSec 2
    } catch { throw 'This project server exists but is not ready. Inspect runtime\server.stderr.log; no duplicate was started.' }
    if ($Health.service -ne 'Khoj Research Lab') { throw 'Project process does not match the service on this port.' }
    if ($LocalModel -and $Status.model -ne 'qwen2.5-1.5b-instruct') {
        throw 'Application already runs with another model. Stop it after current work completes before switching to -LocalModel.'
    }
    Write-Output "Already running for this project: http://127.0.0.1:$Port"
    if ($OpenBrowser) { Start-Process "http://127.0.0.1:$Port" }
    exit 0
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port belongs to another process. Choose another port; no process was stopped."
}
if ($LocalModel) {
    try { $LocalHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8999/health' -TimeoutSec 2 }
    catch { throw 'Start the optional local model first using scripts\start_local_model.ps1.' }
    if ($LocalHealth.status -ne 'ok') { throw 'Optional local model is not ready yet.' }
}
New-Item -ItemType Directory -Path $RuntimePath -Force | Out-Null
$SavedEnvironment = @{}
$Settings = @{ PORT=$Port.ToString() }
if ($LocalModel) {
    $LocalSettings = @{ LLM_BASE_URL='http://127.0.0.1:8999/v1'; LLM_MODEL='qwen2.5-1.5b-instruct'; LLM_API_KEY='local-not-a-secret'; RUN_TIMEOUT_SECONDS='900'; LLM_STRUCTURED_OUTPUT='json_schema' }
    foreach ($Setting in $LocalSettings.GetEnumerator()) { $Settings[$Setting.Key] = $Setting.Value }
}
foreach ($Setting in $Settings.GetEnumerator()) {
    $SavedEnvironment[$Setting.Key] = [Environment]::GetEnvironmentVariable($Setting.Key, 'Process')
    [Environment]::SetEnvironmentVariable($Setting.Key, $Setting.Value, 'Process')
}
try {
    $ServerProcess = Start-Process -FilePath $ProjectPython -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port") -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RuntimePath 'server.stdout.log') -RedirectStandardError (Join-Path $RuntimePath 'server.stderr.log') -PassThru
} finally {
    foreach ($Setting in $SavedEnvironment.GetEnumerator()) { [Environment]::SetEnvironmentVariable($Setting.Key, $Setting.Value, 'Process') }
}
$ServerProcess.Id | Set-Content -LiteralPath (Join-Path $RuntimePath 'server.pid') -Encoding ascii
@{ process_id=$ServerProcess.Id; executable=$ProjectPython; port=$Port;
   start_ticks=$ServerProcess.StartTime.ToUniversalTime().Ticks.ToString(); local_model=[bool]$LocalModel } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $RuntimePath 'server.pid.json') -Encoding utf8
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    Start-Sleep -Milliseconds 500
    if ($ServerProcess.HasExited) { break }
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        if ($Health.ok -and $Health.service -eq 'Khoj Research Lab') {
            Write-Output "Khoj Research Lab is running: http://127.0.0.1:$Port"
            if ($OpenBrowser) { Start-Process "http://127.0.0.1:$Port" }
            exit 0
        }
    } catch { }
}
throw "Startup failed. Inspect $RuntimePath\server.stderr.log"
