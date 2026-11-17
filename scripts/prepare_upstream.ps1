param([switch]$CloneIfMissing, [string]$SourcePath)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = if ($SourcePath) { [IO.Path]::GetFullPath($SourcePath) } else { Join-Path $projectRoot 'upstream\khoj' }
$expectedCommit = 'ae229ca894c0b80ad84664afcfdde523b5e87057'

if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot '.git'))) {
    if (Test-Path -LiteralPath $sourceRoot) {
        $manifest = Get-Content -LiteralPath (Join-Path $projectRoot 'docs\upstream-manifest.json') -Raw | ConvertFrom-Json
        if ($manifest.commit -ne $expectedCommit -or $manifest.repository -ne 'https://github.com/khoj-ai/khoj') {
            throw 'Archive manifest does not identify the expected pinned Khoj source.'
        }
        $requiredSources = @(
            'src/khoj/processor/conversation/utils.py',
            'src/khoj/utils/helpers.py',
            'src/khoj/processor/content/markdown/markdown_to_entries.py',
            'src/khoj/processor/conversation/prompts.py',
            'src/khoj/routers/research.py'
        )
        foreach ($relative in $requiredSources) {
            $expected = $manifest.upstream_source_sha256.PSObject.Properties[$relative].Value
            if (-not $expected -or $expected -notmatch '^[0-9a-f]{64}$') { throw "Missing source hash: $relative" }
            $actual = (Get-FileHash -LiteralPath (Join-Path $sourceRoot $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $expected) { throw "Archive source hash mismatch: $relative. No files were overwritten." }
        }
        $licenseHash = (Get-FileHash -LiteralPath (Join-Path $sourceRoot 'LICENSE') -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($licenseHash -ne '6f1e622c82a380075843bb084a7ec3b1f1d12a4a02526d75e78b0924a860aa75') {
            throw 'Archive LICENSE hash mismatch.'
        }
        Write-Output "Verified pinned Khoj archive source: $expectedCommit"
        Write-Output 'Checked five reused source files and LICENSE; DELIVERY-MANIFEST.json covers remaining shipped files.'
        Write-Output "Location: $sourceRoot"
        exit 0
    }
    if (-not $CloneIfMissing) {
        throw 'Pinned upstream checkout is missing. Re-run with -CloneIfMissing to download it.'
    }
    New-Item -ItemType Directory -Path (Join-Path $projectRoot 'upstream') -Force | Out-Null
    & git init $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
    & git -C $sourceRoot remote add origin 'https://github.com/khoj-ai/khoj.git'
    if ($LASTEXITCODE -ne 0) { throw 'git remote failed' }
    & git -C $sourceRoot fetch --depth 1 origin $expectedCommit
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Khoj download failed' }
    & git -C $sourceRoot checkout --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Khoj checkout failed' }
}

$observedCommit = (& git -C $sourceRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $observedCommit -ne $expectedCommit) {
    throw "Expected Khoj commit $expectedCommit; observed $observedCommit. No files were overwritten."
}
$changes = & git -C $sourceRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect upstream worktree' }
if ($changes) { throw 'Upstream checkout has local changes. Review before reproducing the extraction.' }
Write-Output "Verified pinned Khoj source: $expectedCommit"
Write-Output "Location: $sourceRoot"
