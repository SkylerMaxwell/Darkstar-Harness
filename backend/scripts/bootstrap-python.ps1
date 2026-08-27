# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param(
    [switch]$ProbeOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$PythonVersion = '3.11.9'
$RequiredMajor = 3
$RequiredMinor = 11
$RequiredBits = 64
$InstallerName = 'python-3.11.9-amd64.exe'
$InstallerUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
$ExpectedSha256 = '5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$VendorDirectory = Join-Path $Root 'backend\vendor\python'
$InstallerPath = Join-Path $VendorDirectory $InstallerName
$ReceiptDirectory = Join-Path $Root '.darkstar-runtime'
$ReceiptPath = Join-Path $ReceiptDirectory 'python-install.json'

function Invoke-PythonProbe([string]$Executable, [string[]]$PrefixArgs = @()) {
    if ([string]::IsNullOrWhiteSpace($Executable)) { return $null }
    try {
        if (-not [IO.Path]::IsPathRooted($Executable)) {
            $Command = Get-Command $Executable -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($null -eq $Command) { return $null }
            $Executable = [string]$Command.Source
            $WindowsApps = if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { $null } else { Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps' }
            if ($null -ne $WindowsApps -and $Executable.StartsWith($WindowsApps, [StringComparison]::OrdinalIgnoreCase)) {
                return $null
            }
        }
        $Code = @"
import os, struct, sys
ok = sys.version_info[:2] == ($RequiredMajor, $RequiredMinor) and struct.calcsize('P') * 8 == $RequiredBits
if ok:
    print(os.path.realpath(sys.executable))
raise SystemExit(0 if ok else 9)
"@
        $Arguments = @($PrefixArgs) + @('-B', '-c', $Code)
        $Output = & $Executable @Arguments 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $Resolved = @($Output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)[0]
        if ([string]::IsNullOrWhiteSpace($Resolved)) { return $null }
        $Resolved = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Resolved.Trim()))
        if (-not (Test-Path -LiteralPath $Resolved -PathType Leaf)) { return $null }
        return $Resolved
    } catch { return $null }
}

function Resolve-Python311X64 {
    $Candidates = New-Object System.Collections.Generic.List[object]

    if (-not [string]::IsNullOrWhiteSpace($env:DARKSTAR_PYTHON)) {
        $Candidates.Add(@($env:DARKSTAR_PYTHON, @()))
    }

    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $Candidates.Add(@((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'), @()))
    }

    foreach ($RegistryRoot in @(
        'HKCU:\Software\Python\PythonCore\3.11\InstallPath',
        'HKLM:\Software\Python\PythonCore\3.11\InstallPath',
        'HKLM:\Software\WOW6432Node\Python\PythonCore\3.11\InstallPath'
    )) {
        if (-not (Test-Path -LiteralPath $RegistryRoot)) { continue }
        try {
            $InstallPath = [string](Get-Item -LiteralPath $RegistryRoot -ErrorAction Stop).GetValue('')
            if (-not [string]::IsNullOrWhiteSpace($InstallPath)) {
                $Candidates.Add(@((Join-Path $InstallPath 'python.exe'), @()))
            }
        } catch { }
    }

    $Candidates.Add(@('py.exe', @('-3.11')))
    $Candidates.Add(@('python.exe', @()))
    $Candidates.Add(@('python3.exe', @()))

    $Seen = @{}
    foreach ($Candidate in $Candidates) {
        $Executable = [string]$Candidate[0]
        $PrefixArgs = [string[]]$Candidate[1]
        $Key = ($Executable + '|' + ($PrefixArgs -join ' ')).ToLowerInvariant()
        if ($Seen.ContainsKey($Key)) { continue }
        $Seen[$Key] = $true
        $Resolved = Invoke-PythonProbe $Executable $PrefixArgs
        if ($null -ne $Resolved) { return $Resolved }
    }
    return $null
}

function Resolve-Curl {
    foreach ($Candidate in @((Join-Path $env:SystemRoot 'System32\curl.exe'), 'curl.exe')) {
        if ([string]::IsNullOrWhiteSpace($Candidate)) { continue }
        if ([IO.Path]::IsPathRooted($Candidate)) {
            if (Test-Path -LiteralPath $Candidate -PathType Leaf) { return $Candidate }
        } else {
            $Resolved = Get-Command $Candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($null -ne $Resolved) { return $Resolved.Source }
        }
    }
    return $null
}

function Recover-OfficialInstaller {
    New-Item -ItemType Directory -Force -Path $VendorDirectory | Out-Null
    $Partial = "$InstallerPath.partial-$PID"
    Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
    Write-Host "[Darkstar Harness] Bundled Python installer is missing. Recovering the exact official Python $PythonVersion x64 installer from python.org..."
    try {
        $CurlExe = Resolve-Curl
        if ($null -ne $CurlExe) {
            & $CurlExe --location --fail --show-error --retry 3 --retry-delay 1 --connect-timeout 20 --progress-bar --output $Partial $InstallerUrl
            if ($LASTEXITCODE -ne 0) { throw "curl.exe download failed with exit code $LASTEXITCODE." }
        } else {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri $InstallerUrl -OutFile $Partial
        }
        $Actual = (Get-FileHash -LiteralPath $Partial -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Actual -ne $ExpectedSha256) {
            throw "Downloaded Python installer SHA-256 mismatch. Expected $ExpectedSha256 but received $Actual."
        }
        Move-Item -LiteralPath $Partial -Destination $InstallerPath -Force
    } finally {
        Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
    }
}

function Assert-InstallerIntegrity([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "The Python installer is missing: $Path"
    }
    $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $ExpectedSha256) {
        throw "Python installer SHA-256 mismatch. Expected $ExpectedSha256 but received $Actual. The installer will not be executed."
    }

    $Signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($Signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Python installer Authenticode signature is not valid (status: $($Signature.Status)). The installer will not be executed."
    }
    $Signer = [string]$Signature.SignerCertificate.Subject
    if ($Signer -notmatch 'Python Software Foundation') {
        throw "Python installer signer is unexpected: $Signer. The installer will not be executed."
    }
}

$Existing = Resolve-Python311X64
if ($null -ne $Existing) {
    if ($ProbeOnly) { Write-Output $Existing }
    else { Write-Host "[Darkstar Harness] Python 3.11 x64 is ready: $Existing" }
    exit 0
}

if ($ProbeOnly) { exit 1 }

if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
    # Release archives should carry this exact installer. The recovery path is
    # intentionally pinned to one python.org asset so incomplete source checkouts
    # fail safe rather than selecting an alternate source or a newer Python release.
    Recover-OfficialInstaller
}
Assert-InstallerIntegrity $InstallerPath

Write-Host ''
Write-Host '============================================================'
Write-Host ' Darkstar Python 3.11 prerequisite'
Write-Host '============================================================'
Write-Host "[Darkstar Harness] Python 3.11 x64 was not found."
Write-Host "[Darkstar Harness] Opening the official Python $PythonVersion x64 installer."
Write-Host '[Darkstar Harness] Complete or cancel the installer yourself. Darkstar will wait for the installer window to close.'
Write-Host ''

# Deliberately no unattended-install, feature-selection, PATH, association, or scope
# switches are supplied. The user owns every choice in the official installer UI.
$Process = Start-Process -FilePath $InstallerPath -Wait -PassThru
if ($Process.ExitCode -notin @(0, 3010)) {
    throw "Python installer exited with code $($Process.ExitCode). Python 3.11 is still required to continue."
}

$Installed = Resolve-Python311X64
if ($null -eq $Installed) {
    throw 'The Python installer closed, but Darkstar could not locate a 64-bit Python 3.11 installation. If installation was cancelled, run Darkstar again when ready. If Python was installed, ensure the 64-bit Python 3.11 interpreter was selected.'
}

New-Item -ItemType Directory -Force -Path $ReceiptDirectory | Out-Null
$Receipt = [ordered]@{
    schemaVersion = 1
    requiredSeries = '3.11'
    installerVersion = $PythonVersion
    architecture = 'x64'
    executable = $Installed
    installer = $InstallerName
    source = $InstallerUrl
    sha256 = $ExpectedSha256
    installerExitCode = $Process.ExitCode
    detectedAtUtc = [DateTime]::UtcNow.ToString('o')
}
$Receipt | ConvertTo-Json | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
Write-Host "[Darkstar Harness] Python 3.11 x64 detected successfully: $Installed"
exit 0
