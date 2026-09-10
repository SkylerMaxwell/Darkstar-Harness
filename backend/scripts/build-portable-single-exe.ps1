# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param(
    [string]$OutputDirectory = '',
    [switch]$SkipSourceVerification,
    [switch]$ProvisionMissingRuntimes,
    [switch]$RequireTesseract,
    [string]$ElectronBuilderVersion = '26.0.12'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Fail([string]$Message) { throw "[Darkstar Portable Build] $Message" }
function Info([string]$Message) { Write-Host "[Darkstar Portable Build] $Message" -ForegroundColor Cyan }
function Warn([string]$Message) { Write-Host "[Darkstar Portable Build] $Message" -ForegroundColor Yellow }
function Success([string]$Message) { Write-Host "[Darkstar Portable Build] $Message" -ForegroundColor Green }

# Windows PowerShell 5.1's `Set-Content -Encoding UTF8` emits a UTF-8 BOM.
# electron-builder parses package.json with strict JSON.parse(), which rejects that
# BOM.  All generated build metadata is therefore written explicitly as UTF-8
# without a BOM so the builder behaves identically under Windows PowerShell 5.1
# and modern PowerShell.
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [IO.File]::WriteAllText($Path, $Content, $script:Utf8NoBom)
}

if ($env:OS -ne 'Windows_NT') { Fail 'This builder must be run on 64-bit Windows.' }
if (-not [Environment]::Is64BitOperatingSystem) { Fail 'A 64-bit Windows installation is required.' }

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $Root 'portable-release' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

$BuildCacheRoot = Join-Path $Root '.darkstar-build'
$WorkRoot = Join-Path $BuildCacheRoot 'portable-single-exe-work'
$VerifyStage = Join-Path $WorkRoot 'verify-source'
$Stage = Join-Path $WorkRoot 'app'
$Dist = Join-Path $WorkRoot 'dist'
# Packaging tools are deliberately outside WorkRoot so repeated builds do not
# reinstall electron-builder every time.
$ToolRoot = Join-Path $BuildCacheRoot 'portable-builder-tools'

$Core = Join-Path $Root 'backend\Darkstar_Core.js'
$Renderer = Join-Path $Root 'backend\Darkstar_Renderer.js'
$PolicyPath = Join-Path $Root 'backend\runtime-component-policy.json'
$NativeBootstrap = Join-Path $Root 'backend\scripts\bootstrap-llamacpp.ps1'
$ElectronBootstrap = Join-Path $Root 'backend\scripts\bootstrap-electron.ps1'
$SourceVenv = Join-Path $Root 'venv'
$SourceVenvPython = Join-Path $SourceVenv 'Scripts\python.exe'
$SourceVenvConfig = Join-Path $SourceVenv 'pyvenv.cfg'

foreach ($Required in @($Core, $Renderer, $PolicyPath, $NativeBootstrap, $ElectronBootstrap)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { Fail "Required build input is missing: $Required" }
}
if (-not (Test-Path -LiteralPath $SourceVenvPython -PathType Leaf)) {
    Fail "Darkstar's existing venv was not found at $SourceVenv. Run the normal Darkstar app once so its shared venv exists, then rerun this builder."
}

function Resolve-Application([string[]]$Names) {
    foreach ($Name in $Names) {
        $Command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $Command) { return $Command.Source }
    }
    return $null
}

$Node = Resolve-Application @('node.exe', 'node')
$Npm = Resolve-Application @('npm.cmd', 'npm.exe', 'npm')
$Robo = Resolve-Application @('robocopy.exe')
if (-not $Node -or -not $Npm) { Fail 'Node.js 20+ with npm is required on the build PC only to run electron-builder.' }
if (-not $Robo) { Fail 'robocopy.exe is required to create isolated build staging directories.' }
$NodeMajor = [int]((& $Node -p "process.versions.node.split('.')[0]").Trim())
if ($NodeMajor -lt 20) { Fail "Node.js 20+ is required on the build PC. Found $(& $Node --version)." }

function Copy-TreeFiltered([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { return }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & $Robo $Source $Destination /E /NFL /NDL /NJH /NJS /NP /XD '__pycache__' '.darkstar' '.blacksun' '.darkstar-build' 'node_modules' /XF '*.pyc' '*.pyo' | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "Copying build input failed with robocopy exit code $LASTEXITCODE`: $Source" }
}

function Copy-RuntimeTree([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { Fail "Runtime directory is missing: $Source" }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & $Robo $Source $Destination /E /NFL /NDL /NJH /NJS /NP /XD '__pycache__' /XF '*.pyc' '*.pyo' | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "Copying runtime failed with robocopy exit code $LASTEXITCODE`: $Source" }
}

function Remove-GeneratedArtifacts([string]$Directory) {
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return }
    Get-ChildItem -LiteralPath $Directory -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @('__pycache__', '.darkstar', '.blacksun') } |
        Sort-Object FullName -Descending |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -LiteralPath $Directory -File -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @('.pyc', '.pyo') } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
}

function Get-ExistingVenvDescription {
    try {
        $Probe = & $SourceVenvPython -B -c "import json,platform,struct,sys; print(json.dumps({'prefix':sys.prefix,'base':sys.base_prefix,'version':platform.python_version(),'series':list(sys.version_info[:2]),'bits':struct.calcsize('P')*8}))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $Probe) { Fail 'The existing Darkstar venv Python could not be executed.' }
        $Data = ($Probe | Select-Object -Last 1) | ConvertFrom-Json
        if ([int]$Data.series[0] -ne 3 -or [int]$Data.series[1] -ne 11 -or [int]$Data.bits -ne 64) {
            Fail "Darkstar's existing venv must be 64-bit Python 3.11. Found Python $($Data.version), $($Data.bits)-bit."
        }
        $Base = [IO.Path]::GetFullPath([string]$Data.base)
        if (-not (Test-Path -LiteralPath (Join-Path $Base 'python.exe') -PathType Leaf)) {
            Fail "The existing venv points to a Python base runtime that is no longer present: $Base"
        }
        $IncludeSystem = $false
        if (Test-Path -LiteralPath $SourceVenvConfig -PathType Leaf) {
            $Cfg = Get-Content -LiteralPath $SourceVenvConfig -Raw
            $IncludeSystem = [bool]($Cfg -match '(?im)^\s*include-system-site-packages\s*=\s*true\s*$')
        }
        return [pscustomobject]@{
            Base = $Base
            Version = [string]$Data.version
            IncludeSystemSitePackages = $IncludeSystem
        }
    } catch {
        if ($_.Exception.Message -like '[Darkstar Portable Build]*') { throw }
        Fail "Could not inspect Darkstar's existing venv: $($_.Exception.Message)"
    }
}

$Venv = Get-ExistingVenvDescription
Info "Using the existing Darkstar venv (Python $($Venv.Version)); no pip install or package download will be performed."

$Policy = Get-Content -LiteralPath $PolicyPath -Raw | ConvertFrom-Json
$ElectronVersion = [string]$Policy.electron.version
if ([string]::IsNullOrWhiteSpace($ElectronVersion)) { Fail 'runtime-component-policy.json does not define an Electron version.' }
$ElectronRelativeRoot = [string]$Policy.electron.root
$ElectronSentinel = [string]$Policy.electron.sentinel
$ElectronRoot = Join-Path $Root ($ElectronRelativeRoot -replace '/', '\')
$ElectronExe = Join-Path $ElectronRoot $ElectronSentinel
$BackendBin = Join-Path $Root 'backend\bin'

$AppPackage = Get-Content -LiteralPath (Join-Path $Root 'backend\shell\package.json') -Raw | ConvertFrom-Json
$AppVersion = [string]$AppPackage.version
if ([string]::IsNullOrWhiteSpace($AppVersion)) { $AppVersion = '1.0.0' }

function Get-MissingRuntimeFiles {
    $Required = @(
        $ElectronExe,
        (Join-Path $BackendBin 'backends\cpu\llama-server.exe'),
        (Join-Path $BackendBin 'backends\vulkan\llama-server.exe'),
        (Join-Path $BackendBin 'backends\cuda\llama-server.exe'),
        (Join-Path $BackendBin 'diffusion\cpu\sd-cli.exe'),
        (Join-Path $BackendBin 'diffusion\vulkan\sd-cli.exe')
    )
    return @($Required | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
}

$MissingRuntime = @(Get-MissingRuntimeFiles)
if ($MissingRuntime.Count -gt 0 -and $ProvisionMissingRuntimes) {
    Info 'Some already-used Darkstar runtimes are missing; provisioning only because -ProvisionMissingRuntimes was requested...'
    & $ElectronBootstrap
    if ($LASTEXITCODE -ne 0) { Fail 'Electron runtime bootstrap failed.' }
    & $NativeBootstrap
    if ($LASTEXITCODE -ne 0) { Fail 'Native llama.cpp / stable-diffusion.cpp runtime bootstrap failed.' }
    $MissingRuntime = @(Get-MissingRuntimeFiles)
}
if ($MissingRuntime.Count -gt 0) {
    $List = ($MissingRuntime | ForEach-Object { "`n  - $_" }) -join ''
    Fail "The portable builder reuses Darkstar's existing runtimes and will not silently download replacements. These runtime files are missing:$List`nRun normal Darkstar setup once, or rerun with -ProvisionMissingRuntimes."
}

Remove-Item -LiteralPath $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $VerifyStage, $Stage, $Dist, $ToolRoot | Out-Null

if (-not $SkipSourceVerification) {
    Info 'Creating a clean verification mirror (runtime chats/cache files stay untouched)...'
    foreach ($DirectoryName in @('backend', 'agent_assets', 'custom_nodes', 'workflows', 'launcher')) {
        Copy-TreeFiltered (Join-Path $Root $DirectoryName) (Join-Path $VerifyStage $DirectoryName)
    }
    foreach ($FileName in @('Launch_Darkstar.bat', 'README.md', 'LICENSE.md', 'Rules_For_Agent_Editors.md', 'Index_for_Agents.txt')) {
        $Source = Join-Path $Root $FileName
        if (Test-Path -LiteralPath $Source -PathType Leaf) { Copy-Item -LiteralPath $Source -Destination (Join-Path $VerifyStage $FileName) -Force }
    }
    Remove-GeneratedArtifacts $VerifyStage
    $VerifyCore = Join-Path $VerifyStage 'backend\Darkstar_Core.js'
    Info 'Verifying the clean source mirror before packaging...'
    & $Node $VerifyCore '--darkstar-command=check'
    if ($LASTEXITCODE -ne 0) { Fail 'Darkstar source verification failed in the isolated build mirror. Your live projects/chats were not modified.' }
    Remove-Item -LiteralPath $VerifyStage -Recurse -Force -ErrorAction SilentlyContinue
}

Info 'Staging Darkstar application files without projects, chats, caches, or build artifacts...'
foreach ($DirectoryName in @('backend', 'agent_assets', 'custom_nodes', 'workflows')) {
    Copy-TreeFiltered (Join-Path $Root $DirectoryName) (Join-Path $Stage $DirectoryName)
}
foreach ($FileName in @('README.md', 'LICENSE.md', 'Rules_For_Agent_Editors.md', 'Index_for_Agents.txt')) {
    $Source = Join-Path $Root $FileName
    if (Test-Path -LiteralPath $Source -PathType Leaf) { Copy-Item -LiteralPath $Source -Destination (Join-Path $Stage $FileName) -Force }
}
Remove-GeneratedArtifacts $Stage
Remove-Item -LiteralPath (Join-Path $Stage 'backend\Dev') -Recurse -Force -ErrorAction SilentlyContinue
# electron-builder receives the already-provisioned Electron distribution through
# electronDist; keeping a second copy inside app resources would only duplicate it.
Remove-Item -LiteralPath (Join-Path $Stage 'backend\vendor\electron') -Recurse -Force -ErrorAction SilentlyContinue

Info 'Snapshotting the existing Darkstar venv exactly as currently used...'
$PortableVenv = Join-Path $Stage 'venv'
Copy-RuntimeTree $SourceVenv $PortableVenv

Info "Bundling the Python base runtime used by that venv: $($Venv.Base)"
$PortablePythonRoot = Join-Path $Stage 'backend\vendor\python-portable'
Remove-Item -LiteralPath $PortablePythonRoot -Recurse -Force -ErrorAction SilentlyContinue
Copy-RuntimeTree $Venv.Base $PortablePythonRoot
$PortablePython = Join-Path $PortablePythonRoot 'python.exe'
if (-not (Test-Path -LiteralPath $PortablePython -PathType Leaf)) { Fail 'The staged Python base runtime is missing python.exe.' }

# Some existing Darkstar tools intentionally invoke an external `node` command
# (for example Three.js inspection). Bundle the exact Node executable already used
# on the build PC; this is a file copy, not an npm/runtime dependency install.
Info 'Bundling the existing Node executable used by Node-backed agent utilities...'
$NodeRuntimeDir = Join-Path $Stage 'backend\vendor\node'
New-Item -ItemType Directory -Force -Path $NodeRuntimeDir | Out-Null
Copy-Item -LiteralPath $Node -Destination (Join-Path $NodeRuntimeDir 'node.exe') -Force

# Tesseract is optional in normal Darkstar: pdf_tools.py detects whether its native
# executable exists. Preserve that behavior. If it is installed, include it; if not,
# do not invent a new mandatory build dependency.
$Tesseract = Resolve-Application @('tesseract.exe', 'tesseract')
if (-not $Tesseract) {
    $KnownTesseract = Join-Path $env:ProgramFiles 'Tesseract-OCR\tesseract.exe'
    if (Test-Path -LiteralPath $KnownTesseract -PathType Leaf) { $Tesseract = $KnownTesseract }
}
if ($Tesseract) {
    Info 'Tesseract is installed locally; bundling the existing OCR runtime.'
    $TesseractSourceRoot = Split-Path -Parent $Tesseract
    $TesseractTargetRoot = Join-Path $Stage 'backend\vendor\tesseract'
    Copy-RuntimeTree $TesseractSourceRoot $TesseractTargetRoot
} elseif ($RequireTesseract) {
    Fail 'Tesseract was explicitly required with -RequireTesseract, but no local Tesseract installation was found.'
} else {
    Warn 'Tesseract is not installed on this PC, so no Tesseract binary will be embedded. Darkstar will behave exactly as it does now: OCR reports unavailable unless Tesseract exists on the destination PATH.'
}

$IncludeSystemText = if ($Venv.IncludeSystemSitePackages) { 'true' } else { 'false' }
$PortableEntry = @'
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { app } = require('electron');

function writableDirectory(directory) {
    try {
        fs.mkdirSync(directory, { recursive: true });
        const probe = path.join(directory, `.darkstar-portable-probe-${process.pid}-${Date.now()}`);
        fs.writeFileSync(probe, 'ok', { flag: 'wx' });
        fs.unlinkSync(probe);
        return true;
    } catch (_) { return false; }
}

const executableDirectory = String(process.env.PORTABLE_EXECUTABLE_DIR || '').trim();
if (!executableDirectory) {
    throw new Error('Darkstar portable startup could not resolve the directory containing Darkstar-Portable.exe.');
}
if (!writableDirectory(executableDirectory)) {
    throw new Error(`Darkstar-Portable.exe must be run from a writable folder so projects, models, settings, and chats stay portable: ${executableDirectory}`);
}

process.env.DARKSTAR_ROOT = executableDirectory;
process.env.DARKSTAR_PORTABLE_DATA_ROOT = executableDirectory;
const portableUserData = path.join(executableDirectory, '.darkstar-user-data');
fs.mkdirSync(portableUserData, { recursive: true });
app.setPath('userData', portableUserData);

const appRoot = __dirname;
const pythonRoot = path.join(appRoot, 'backend', 'vendor', 'python-portable');
const pythonExe = path.join(pythonRoot, 'python.exe');
const venvRoot = path.join(appRoot, 'venv');
const venvPython = path.join(venvRoot, 'Scripts', 'python.exe');
if (!fs.existsSync(pythonExe) || !fs.existsSync(venvPython)) {
    throw new Error('The portable package is missing its snapshotted Darkstar Python environment.');
}

// A Windows venv is relocatable when its Python base is shipped with it and
// pyvenv.cfg is repointed after the portable EXE extracts. No packages are
// installed or upgraded here.
const cfg = [
    `home = ${pythonRoot}`,
    'include-system-site-packages = __INCLUDE_SYSTEM_SITE_PACKAGES__',
    'version = __PYTHON_VERSION__',
    `executable = ${pythonExe}`,
    `command = ${pythonExe} -m venv ${venvRoot}`,
    '',
].join('\r\n');
fs.writeFileSync(path.join(venvRoot, 'pyvenv.cfg'), cfg, 'utf8');
process.env.DARKSTAR_PYTHON = pythonExe;

const pathParts = [
    path.join(venvRoot, 'Scripts'),
    path.join(appRoot, 'backend', 'vendor', 'node'),
];
const tesseractRoot = path.join(appRoot, 'backend', 'vendor', 'tesseract');
if (fs.existsSync(path.join(tesseractRoot, 'tesseract.exe'))) {
    pathParts.push(tesseractRoot);
    const tessdata = path.join(tesseractRoot, 'tessdata');
    if (fs.existsSync(tessdata)) process.env.TESSDATA_PREFIX = tessdata;
}
pathParts.push(String(process.env.PATH || ''));
process.env.PATH = pathParts.filter(Boolean).join(path.delimiter);
process.env.DARKSTAR_PORTABLE_BUILD = '1';

require('./backend/Darkstar_Core.js');
'@
$PortableEntry = $PortableEntry.Replace('__INCLUDE_SYSTEM_SITE_PACKAGES__', $IncludeSystemText).Replace('__PYTHON_VERSION__', $Venv.Version)
Write-Utf8NoBom -Path (Join-Path $Stage 'portable-entry.js') -Content $PortableEntry

$PackageJson = [ordered]@{
    name = 'darkstar-portable-build'
    version = $AppVersion
    private = $true
    main = 'portable-entry.js'
    description = 'Darkstar portable single-executable build'
    build = [ordered]@{
        appId = 'com.darkstar.chat'
        productName = 'Darkstar'
        asar = $false
        compression = 'maximum'
        npmRebuild = $false
        electronVersion = $ElectronVersion
        electronDist = $ElectronRoot
        directories = [ordered]@{ output = $Dist }
        files = @(
            '**/*',
            '!node_modules/**',
            '!backend/Dev/**',
            '!.darkstar-build/**'
        )
        win = [ordered]@{
            target = @([ordered]@{ target = 'portable'; arch = @('x64') })
            icon = 'backend/assets/Darkstar.ico'
            artifactName = "Darkstar-Portable-$AppVersion.exe"
        }
        portable = [ordered]@{
            artifactName = "Darkstar-Portable-$AppVersion.exe"
            requestExecutionLevel = 'user'
        }
    }
}
$GeneratedPackagePath = Join-Path $Stage 'package.json'
Write-Utf8NoBom -Path $GeneratedPackagePath -Content ($PackageJson | ConvertTo-Json -Depth 12)

# Validate with the same strict JSON semantics electron-builder uses before it
# gets a chance to mutate/copy package.json.  This catches BOM/encoding regressions
# immediately with a useful Darkstar error instead of a deep builder stack trace.
& $Node -e "const fs=require('fs');const p=process.argv[1];const b=fs.readFileSync(p);if(b.length>=3&&b[0]===0xef&&b[1]===0xbb&&b[2]===0xbf)throw new Error('UTF-8 BOM detected');JSON.parse(b.toString('utf8'));" $GeneratedPackagePath
if ($LASTEXITCODE -ne 0) { Fail 'Generated portable package.json is not strict UTF-8 JSON without a BOM.' }

$Builder = Join-Path $ToolRoot 'node_modules\.bin\electron-builder.cmd'
if (-not (Test-Path -LiteralPath $Builder -PathType Leaf)) {
    Info "Installing electron-builder $ElectronBuilderVersion once into the persistent local build-tools cache..."
    New-Item -ItemType Directory -Force -Path $ToolRoot | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $ToolRoot 'package.json') -PathType Leaf)) {
        '{"private":true}' | Set-Content -LiteralPath (Join-Path $ToolRoot 'package.json') -Encoding ASCII
    }
    & $Npm install --prefix $ToolRoot --no-audit --no-fund --save-exact "electron-builder@$ElectronBuilderVersion"
    if ($LASTEXITCODE -ne 0) { Fail 'npm could not install electron-builder, which is the local packaging tool. No Darkstar runtime packages were installed or modified.' }
}
if (-not (Test-Path -LiteralPath $Builder -PathType Leaf)) { Fail 'electron-builder.cmd was not found after packaging-tool setup.' }

Push-Location $Stage
try {
    Info 'Building one Windows x64 portable EXE from the staged Darkstar runtime snapshot...'
    & $Builder --win portable --x64
    if ($LASTEXITCODE -ne 0) { Fail 'electron-builder failed.' }
} finally {
    Pop-Location
}

$Artifact = Get-ChildItem -LiteralPath $Dist -Filter 'Darkstar-Portable-*.exe' -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $Artifact) { Fail 'Build completed without producing the expected portable EXE.' }

Remove-Item -LiteralPath $OutputDirectory -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$FinalExe = Join-Path $OutputDirectory 'Darkstar-Portable.exe'
Copy-Item -LiteralPath $Artifact.FullName -Destination $FinalExe -Force

$Manifest = [ordered]@{
    schemaVersion = 2
    buildType = 'electron-builder-portable-existing-runtime-snapshot'
    architecture = 'windows-x64'
    appVersion = $AppVersion
    electronVersion = $ElectronVersion
    executable = 'Darkstar-Portable.exe'
    executableSha256 = (Get-FileHash -LiteralPath $FinalExe -Algorithm SHA256).Hash.ToLowerInvariant()
    sourceMonoliths = [ordered]@{
        'backend/Darkstar_Core.js' = (Get-FileHash -LiteralPath $Core -Algorithm SHA256).Hash.ToLowerInvariant()
        'backend/Darkstar_Renderer.js' = (Get-FileHash -LiteralPath $Renderer -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    python = [ordered]@{
        sourceVenv = $SourceVenv
        sourceBase = $Venv.Base
        version = $Venv.Version
        includeSystemSitePackages = $Venv.IncludeSystemSitePackages
        packagesReinstalled = $false
    }
    bundled = [ordered]@{
        electron = $true
        llamaCpp = $true
        stableDiffusionCpp = $true
        existingDarkstarVenv = $true
        pythonBaseRuntime = $true
        nodeRuntime = $true
        tesseract = (Test-Path -LiteralPath (Join-Path $Stage 'backend\vendor\tesseract\tesseract.exe') -PathType Leaf)
    }
    notes = @(
        'No pip install, pip upgrade, or Python package download occurs during this build.',
        'The existing Darkstar venv and the Python base interpreter it actually uses are snapshotted into the portable EXE.',
        'Model files and project/chat user data are not embedded.',
        'Tesseract is bundled only when already installed on the build PC, unless -RequireTesseract is specified.'
    )
}
$ManifestPath = Join-Path $BuildCacheRoot 'Darkstar-Portable-Build.json'
Write-Utf8NoBom -Path $ManifestPath -Content ($Manifest | ConvertTo-Json -Depth 10)

Success "Portable EXE created: $FinalExe"
Success "SHA-256: $($Manifest.executableSha256)"
Info "Build manifest: $ManifestPath"
Write-Host ''
Write-Host 'The build reused Darkstar''s existing venv and native runtimes. It did not reinstall Python packages.'
