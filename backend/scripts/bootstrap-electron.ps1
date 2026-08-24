# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ElectronVersion = '43.2.0'
$AssetName = 'electron-v43.2.0-win32-x64.zip'
$AssetUrl = 'https://github.com/electron/electron/releases/download/v43.2.0/electron-v43.2.0-win32-x64.zip'
$ExpectedSha256 = 'eba5f5088af40ecb364fe258809c79a5234c6ece5a75c64722772eba01b02786'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Destination = Join-Path $Root 'backend\vendor\electron\win32-x64'
$CacheDirectory = Join-Path $Root '.darkstar-runtime\electron-cache'
$CachedZip = Join-Path $CacheDirectory $AssetName
$RequiredFiles = @(
    'electron.exe', 'version', 'icudtl.dat', 'resources.pak', 'snapshot_blob.bin',
    'v8_context_snapshot.bin', 'locales\en-US.pak', 'LICENSE', 'LICENSES.chromium.html'
)

function Test-ElectronRuntime([string]$Directory) {
    try {
        foreach ($Relative in $RequiredFiles) {
            if (-not (Test-Path -LiteralPath (Join-Path $Directory $Relative) -PathType Leaf)) { return $false }
        }
        $Version = (Get-Content -LiteralPath (Join-Path $Directory 'version') -Raw).Trim()
        if ($Version -ne $ElectronVersion) { return $false }
        if ((Get-Item -LiteralPath (Join-Path $Directory 'electron.exe')).Length -lt 100MB) { return $false }
        return $true
    } catch { return $false }
}

function Test-PinnedArchive([string]$Archive) {
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) { return $false }
    try {
        $Actual = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
        return $Actual -eq $ExpectedSha256
    } catch { return $false }
}

if (Test-ElectronRuntime $Destination) {
    Write-Host "[Darkstar Harness] Electron $ElectronVersion is ready."
    exit 0
}

New-Item -ItemType Directory -Force -Path $CacheDirectory | Out-Null
if (-not (Test-PinnedArchive $CachedZip)) {
    Remove-Item -LiteralPath $CachedZip -Force -ErrorAction SilentlyContinue
    $Partial = "$CachedZip.partial-$PID"
    Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
    Write-Host "[Darkstar Harness] Downloading Electron $ElectronVersion Windows x64 from the official Electron GitHub release..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri $AssetUrl -OutFile $Partial
        $Actual = (Get-FileHash -LiteralPath $Partial -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Actual -ne $ExpectedSha256) {
            throw "Electron archive SHA-256 mismatch. Expected $ExpectedSha256 but received $Actual. The file will not be installed."
        }
        Move-Item -LiteralPath $Partial -Destination $CachedZip -Force
    } catch {
        Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
        throw
    }
} else {
    Write-Host "[Darkstar Harness] Using the verified cached Electron $ElectronVersion archive."
}

$StagingParent = Join-Path $Root '.darkstar-runtime\electron-staging'
$Staging = Join-Path $StagingParent ("electron-$PID-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Staging | Out-Null
try {
    Write-Host '[Darkstar Harness] Verifying and extracting Electron...'
    Expand-Archive -LiteralPath $CachedZip -DestinationPath $Staging -Force
    if (-not (Test-ElectronRuntime $Staging)) {
        throw 'The verified Electron archive extracted, but its runtime layout failed Darkstar Harness validation.'
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
    Move-Item -LiteralPath $Staging -Destination $Destination
    $Receipt = [ordered]@{
        schemaVersion = 1
        electronVersion = $ElectronVersion
        asset = $AssetName
        source = $AssetUrl
        sha256 = $ExpectedSha256
        installedAtUtc = [DateTime]::UtcNow.ToString('o')
    }
    $Receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Destination '.darkstar-bootstrap.json') -Encoding UTF8
} finally {
    if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue }
}

if (-not (Test-ElectronRuntime $Destination)) { throw 'Electron bootstrap completed but final runtime validation failed.' }
Write-Host "[Darkstar Harness] Electron $ElectronVersion installed and verified."
