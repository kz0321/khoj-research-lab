param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    & $Python -c "import sys; assert (3,10) <= sys.version_info < (3,13), 'Use Python 3.10, 3.11 or 3.12'"
    if ($LASTEXITCODE -ne 0) { throw 'Compatible Python required. Pass -Python with the full executable path.' }
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
    & '.\.venv\Scripts\python.exe' -c "from app.retrieval import embed; print('Embedding ready:', embed(['Setup check']).shape)"
    if ($LASTEXITCODE -ne 0) { throw 'Embedding model download failed; retry with internet access.' }
    Write-Output 'Setup complete. Configure .env, then run scripts\start.ps1 -OpenBrowser.'
} finally { Pop-Location }
