param(
    [ValidateSet('vulkan', 'cpu')][string]$Backend = 'vulkan',
    [ValidateRange(1024, 32768)][int]$ContextSize = 16384,
    [ValidateRange(1, 32)][int]$Threads = 8,
    [ValidateRange(1024, 65535)][int]$Port = 8999
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$localRoot = Join-Path $projectRoot 'runtime\local-model'
$backendRoot = Join-Path $localRoot "llama\$Backend"
$modelPath = Join-Path $projectRoot 'models\generative\qwen2.5-1.5b-instruct-q4_k_m.gguf'
$executable = Get-ChildItem -LiteralPath $backendRoot -Filter 'llama-server.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $executable -or -not (Test-Path -LiteralPath $modelPath)) {
    throw 'Run .venv\Scripts\python.exe scripts\setup_local_model.py before starting the local model.'
}
$pidFile = Join-Path $localRoot 'server.pid.json'
if (Test-Path -LiteralPath $pidFile) {
    $previous = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    $existing = Get-Process -Id $previous.process_id -ErrorAction SilentlyContinue
    if ($existing -and $existing.Path -eq $previous.executable -and $existing.StartTime.ToUniversalTime().Ticks.ToString() -eq $previous.start_ticks) {
        if ($previous.backend -ne $Backend -or $previous.context_size -ne $ContextSize -or $previous.threads -ne $Threads -or $previous.port -ne $Port) {
            throw 'A local model is already running with different settings. Run scripts\stop_local_model.ps1 before changing its configuration.'
        }
        Write-Output "Local model already running: http://127.0.0.1:$($previous.port)/v1 (PID $($existing.Id))"
        exit 0
    }
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use; no existing service was stopped."
}
$gpuLayers = if ($Backend -eq 'vulkan') { '99' } else { '0' }
$arguments = @('--model', ('"{0}"' -f $modelPath), '--alias', 'qwen2.5-1.5b-instruct',
    '--host', '127.0.0.1', '--port', $Port.ToString(), '--ctx-size', $ContextSize.ToString(),
    '--threads', $Threads.ToString(), '--parallel', '1', '--n-gpu-layers', $gpuLayers, '--jinja')
if ($Backend -eq 'vulkan') { $arguments += @('--device', 'Vulkan0') }
$process = Start-Process -FilePath $executable.FullName -ArgumentList $arguments -WorkingDirectory $executable.DirectoryName `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localRoot 'server.stdout.log') `
    -RedirectStandardError (Join-Path $localRoot 'server.stderr.log')
$record = @{ process_id = $process.Id; executable = $executable.FullName; start_ticks = $process.StartTime.ToUniversalTime().Ticks.ToString();
    port = $Port; backend = $Backend; device = $(if ($Backend -eq 'vulkan') { 'Vulkan0' } else { 'CPU' });
    context_size = $ContextSize; threads = $Threads; model_alias = 'qwen2.5-1.5b-instruct' }
$record | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
$ready = $false
for ($attempt = 0; $attempt -lt 45; $attempt++) {
    if ($process.HasExited) { throw "Local model exited. Inspect runtime\local-model\server.stderr.log; try -Backend cpu if Vulkan is unavailable." }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($health.status -eq 'ok') { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 1000
}
if (-not $ready) { throw 'The model is still loading; inspect the local model log and /health endpoint.' }
Write-Output "Local model ready: http://127.0.0.1:$Port/v1"
Write-Output "Backend: $Backend; model: qwen2.5-1.5b-instruct; PID: $($process.Id)"
Write-Output 'App .env and the research application server were not changed.'
