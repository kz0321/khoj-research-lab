$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pidFile = Join-Path $projectRoot 'runtime\local-model\server.pid.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No recorded local model process.'; exit 0 }
$record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
$process = Get-Process -Id $record.process_id -ErrorAction SilentlyContinue
if ($process) {
    $expectedRoot = (Resolve-Path -LiteralPath (Join-Path $projectRoot 'runtime\local-model\llama')).Path + [IO.Path]::DirectorySeparatorChar
    if (-not $record.executable.StartsWith($expectedRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $process.Path -ne $record.executable -or
        $process.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.start_ticks) {
        throw 'Recorded PID no longer matches the project local-model process; nothing was stopped.'
    }
    Stop-Process -Id $process.Id
    Write-Output "Stopped local model PID $($process.Id)."
} else { Write-Output 'Recorded local model is no longer running.' }
Remove-Item -LiteralPath $pidFile
