param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) { throw 'Install project dependencies first, or pass -Python with the Python executable.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 24 is required for the frontend checks.' }
Push-Location $ProjectRoot
try {
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency checks failed.' }
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Python regression checks failed.' }
    $FrontendTests = @(Get-ChildItem -LiteralPath 'tests' -Filter 'frontend_*.test.cjs' | ForEach-Object { $_.FullName })
    & node --test @FrontendTests
    if ($LASTEXITCODE -ne 0) { throw 'Frontend regression checks failed.' }
    & $Python -c "import json; from eval.check_data import validate; print(json.dumps(validate(), ensure_ascii=False, indent=2))"
    if ($LASTEXITCODE -ne 0) { throw 'Dataset integrity checks failed.' }
    Write-Output 'All checks passed. These checks do not call a paid model or measure answer quality.'
} finally { Pop-Location }
