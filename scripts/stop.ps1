$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$PidFile = Join-Path $ProjectRoot 'runtime\server.pid'
$RecordFile = Join-Path $ProjectRoot 'runtime\server.pid.json'
$Record = $null
if (Test-Path -LiteralPath $RecordFile) {
    $Record = Get-Content -LiteralPath $RecordFile -Raw | ConvertFrom-Json
    $ServerId = [int]$Record.process_id
} elseif (Test-Path -LiteralPath $PidFile) {
    # Compatibility with the initial deployment's numeric PID record.
    $ServerId = [int](Get-Content -LiteralPath $PidFile)
} else { Write-Output 'No project server PID recorded.'; exit 0 }
$ServerInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$ServerId"
if (-not $ServerInfo) { Write-Output 'Project server is already stopped.'; exit 0 }
$ExpectedPython = [IO.Path]::GetFullPath((Join-Path $ProjectRoot '.venv\Scripts\python.exe'))
if ($ServerInfo.ExecutablePath -ne $ExpectedPython -or
    $ServerInfo.CommandLine -notmatch '(?:^|\s)-m\s+uvicorn\s+app\.main:app(?:\s|$)') {
    throw 'PID ownership check failed. Refusing to stop another process.'
}
if ($Record) {
    $Process = Get-Process -Id $ServerId
    if ($Record.executable -ne $ExpectedPython -or
        $Process.StartTime.ToUniversalTime().Ticks.ToString() -ne $Record.start_ticks) {
        throw 'Recorded process identity/start time no longer matches. No process was stopped.'
    }
}
Stop-Process -Id $ServerId
foreach ($Path in @($PidFile, $RecordFile)) {
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path }
}
Write-Output 'Stopped the project server. Database and history were retained.'
