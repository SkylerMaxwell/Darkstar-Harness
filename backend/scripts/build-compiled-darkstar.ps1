# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param(
    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root 'binary'
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)

$core = Join-Path $root 'backend\Darkstar_Core.js'
$renderer = Join-Path $root 'backend\Darkstar_Renderer.js'
$launcherSource = Join-Path $root 'launcher\compiled\main_windows.go'

foreach ($required in @($core, $renderer, $launcherSource)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required build input is missing: $required"
    }
}

$go = Get-Command go.exe -ErrorAction SilentlyContinue
if (-not $go) { $go = Get-Command go -ErrorAction SilentlyContinue }
if (-not $go) {
    throw 'Go 1.22+ was not found. Install Go, then rerun build-compiled-darkstar.ps1.'
}

$stage = Join-Path $root '.darkstar-build\compiled-core'
Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'embedded') | Out-Null
Copy-Item -LiteralPath $launcherSource -Destination (Join-Path $stage 'main_windows.go') -Force
Set-Content -LiteralPath (Join-Path $stage 'go.mod') -Encoding ASCII -Value "module darkstar-compiled-launcher`r`n`r`ngo 1.22`r`n"

function Write-GzipFile([string]$Source, [string]$Destination) {
    $input = [System.IO.File]::OpenRead($Source)
    try {
        $output = [System.IO.File]::Create($Destination)
        try {
            $gzip = New-Object System.IO.Compression.GZipStream($output, [System.IO.Compression.CompressionLevel]::Optimal, $false)
            try { $input.CopyTo($gzip) } finally { $gzip.Dispose() }
        } finally { $output.Dispose() }
    } finally { $input.Dispose() }
}

Write-GzipFile $core (Join-Path $stage 'embedded\Darkstar_Core.js.gz')
Write-GzipFile $renderer (Join-Path $stage 'embedded\Darkstar_Renderer.js.gz')

Remove-Item -LiteralPath $OutputDirectory -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$previousGOOS = $env:GOOS
$previousGOARCH = $env:GOARCH
$previousCGO = $env:CGO_ENABLED
try {
    $env:GOOS = 'windows'
    $env:GOARCH = 'amd64'
    $env:CGO_ENABLED = '0'
    Push-Location $stage
    try {
        & $go.Source build -trimpath -ldflags '-s -w -H=windowsgui' -o (Join-Path $OutputDirectory 'Darkstar.exe') .
        if ($LASTEXITCODE -ne 0) { throw "Go failed to build Darkstar.exe (exit $LASTEXITCODE)." }
    } finally { Pop-Location }
} finally {
    $env:GOOS = $previousGOOS
    $env:GOARCH = $previousGOARCH
    $env:CGO_ENABLED = $previousCGO
}

# Copy the transparent runtime distribution. The two monolith source files are
# intentionally omitted because they are embedded in Darkstar.exe.
foreach ($dirName in @('backend', 'agent_assets', 'custom_nodes', 'workflows')) {
    $sourceDir = Join-Path $root $dirName
    if (Test-Path -LiteralPath $sourceDir -PathType Container) {
        Copy-Item -LiteralPath $sourceDir -Destination $OutputDirectory -Recurse -Force
    }
}
Remove-Item -LiteralPath (Join-Path $OutputDirectory 'backend\Darkstar_Core.js') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $OutputDirectory 'backend\Darkstar_Renderer.js') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $OutputDirectory 'backend\Dev') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $OutputDirectory 'backend\scripts\build-compiled-darkstar.ps1') -Force -ErrorAction SilentlyContinue

foreach ($fileName in @('README.md', 'LICENSE.md', 'runtime-component-policy.json')) {
    $sourceFile = Join-Path $root $fileName
    if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
        Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $OutputDirectory $fileName) -Force
    }
}

$launcherBat = @'
@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "DARKSTAR_ROOT=%~dp0"
start "" "%DARKSTAR_ROOT%Darkstar.exe" %*
if errorlevel 1 (
  echo [Darkstar] ERROR: Could not start Darkstar.exe.
  pause >nul
  exit /b 1
)
exit /b 0
'@
Set-Content -LiteralPath (Join-Path $OutputDirectory 'Launch_Darkstar.bat') -Value $launcherBat -Encoding ASCII

$coreHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $core).Hash.ToLowerInvariant()
$rendererHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $renderer).Hash.ToLowerInvariant()
$exeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $OutputDirectory 'Darkstar.exe')).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    schemaVersion = 1
    architecture = 'windows-x64'
    executable = 'Darkstar.exe'
    executableSha256 = $exeHash
    embeddedMonoliths = [ordered]@{
        'backend/Darkstar_Core.js' = $coreHash
        'backend/Darkstar_Renderer.js' = $rendererHash
    }
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'COMPILED_CORE_MANIFEST.json') -Encoding UTF8

Write-Host "Built compiled Darkstar distribution: $OutputDirectory"
Write-Host "Darkstar.exe SHA-256: $exeHash"
