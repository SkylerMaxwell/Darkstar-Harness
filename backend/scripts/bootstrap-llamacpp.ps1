# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$PolicyPath = Join-Path $Root 'backend\runtime-component-policy.json'
$Destination = Join-Path $Root 'backend\bin'
$BackendsDestination = Join-Path $Destination 'backends'
$ReceiptPath = Join-Path $Destination '.darkstar-bootstrap.json'

if (-not (Test-Path -LiteralPath $PolicyPath -PathType Leaf)) {
    throw "Runtime policy is missing: $PolicyPath"
}

$Policy = Get-Content -LiteralPath $PolicyPath -Raw | ConvertFrom-Json
$Bootstrap = $Policy.backendBin.bootstrap
if ($null -eq $Bootstrap) { throw 'backend/runtime-component-policy.json does not define backendBin.bootstrap.' }

$BundleVersion = [int]$Bootstrap.bundleVersion
$LlamaBuild = [string]$Bootstrap.build
$LlamaCommit = [string]$Bootstrap.commit
$CudaRelease = [string]$Bootstrap.cudaRelease
$BackendPins = $Bootstrap.backends
$NoticeDownloads = @($Bootstrap.noticeDownloads)
$BackendOrder = @('cpu', 'vulkan', 'cuda')

if ($BundleVersion -ne 2) { throw 'The llama.cpp bootstrap bundle schema must be version 2.' }
if ([string]::IsNullOrWhiteSpace($LlamaBuild) -or [string]::IsNullOrWhiteSpace($LlamaCommit) -or [string]::IsNullOrWhiteSpace($CudaRelease)) {
    throw 'The llama.cpp bootstrap pin is incomplete.'
}
foreach ($BackendName in $BackendOrder) {
    if ($null -eq $BackendPins.$BackendName) { throw "The llama.cpp bootstrap is missing the $BackendName backend pin." }
    if (@($BackendPins.$BackendName.archives).Count -lt 1) { throw "The llama.cpp $BackendName backend has no pinned release archive." }
}
if (@($BackendPins.cpu.archives).Count -ne 1) { throw 'The CPU backend must define exactly one pinned release archive.' }
if (@($BackendPins.vulkan.archives).Count -ne 1) { throw 'The Vulkan backend must define exactly one pinned release archive.' }
if (@($BackendPins.cuda.archives).Count -ne 2) { throw 'The CUDA backend must define exactly two pinned release archives (llama.cpp + CUDA runtime).' }
if ($NoticeDownloads.Count -ne 2) { throw 'The llama.cpp bootstrap must define exactly two pinned notice downloads.' }

$CacheDirectory = Join-Path $Root ('.darkstar-runtime\llama-cache\{0}-all-backends' -f $LlamaBuild)
$StagingParent = Join-Path $Root '.darkstar-runtime\llama-staging'
$CommonRequiredFiles = @('llama-server.exe', 'llama-server-impl.dll', 'llama.dll', 'llama-common.dll', 'ggml.dll', 'ggml-base.dll')
$RequiredCudaFiles = @('ggml-cuda.dll', 'cudart64_12.dll', 'cublas64_12.dll', 'cublasLt64_12.dll')
$RequiredVulkanFiles = @('ggml-vulkan.dll')

function Assert-PinnedHttpsUrl([string]$Url, [string[]]$AllowedHosts) {
    $Uri = [Uri]$Url
    if ($Uri.Scheme -ne 'https') { throw "Bootstrap download must use HTTPS: $Url" }
    if ($AllowedHosts -notcontains $Uri.Host.ToLowerInvariant()) {
        throw "Bootstrap download host is not approved: $($Uri.Host)"
    }
}

function Test-PinnedFile([string]$FilePath, [string]$ExpectedSha256) {
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) { return $false }
    try {
        $Actual = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
        return $Actual -eq ([string]$ExpectedSha256).ToLowerInvariant()
    } catch { return $false }
}

function Invoke-DarkstarDownload([string]$Url, [string]$Destination) {
    $CurlCandidates = @(
        (Join-Path $env:SystemRoot 'System32\curl.exe'),
        'curl.exe'
    )
    $CurlExe = $null
    foreach ($Candidate in $CurlCandidates) {
        if ([string]::IsNullOrWhiteSpace($Candidate)) { continue }
        if ([IO.Path]::IsPathRooted($Candidate)) {
            if (Test-Path -LiteralPath $Candidate -PathType Leaf) { $CurlExe = $Candidate; break }
        } else {
            $Resolved = Get-Command $Candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($null -ne $Resolved) { $CurlExe = $Resolved.Source; break }
        }
    }

    if ($null -ne $CurlExe) {
        Write-Host '[Darkstar Harness] Download progress:'
        $CurlArguments = @(
            '--location', '--fail', '--show-error',
            '--retry', '3', '--retry-delay', '1',
            '--connect-timeout', '20',
            '--progress-bar',
            '--output', $Destination,
            $Url
        )
        & $CurlExe @CurlArguments
        if ($LASTEXITCODE -ne 0) { throw "curl.exe download failed with exit code $LASTEXITCODE." }
        return
    }

    Write-Host '[Darkstar Harness] curl.exe is unavailable; using the compatibility downloader.'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $PreviousProgressPreference = $ProgressPreference
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
    } finally {
        $ProgressPreference = $PreviousProgressPreference
    }
}

function Get-VerifiedDownload($Asset, [string[]]$AllowedHosts) {
    $Name = [string]$Asset.asset
    $Url = [string]$Asset.url
    $ExpectedSha256 = ([string]$Asset.sha256).ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($Name) -or [string]::IsNullOrWhiteSpace($Url) -or $ExpectedSha256 -notmatch '^[a-f0-9]{64}$') {
        throw 'A llama.cpp bootstrap asset has incomplete pin metadata.'
    }
    Assert-PinnedHttpsUrl $Url $AllowedHosts
    New-Item -ItemType Directory -Force -Path $CacheDirectory | Out-Null
    $Cached = Join-Path $CacheDirectory $Name
    if (Test-PinnedFile $Cached $ExpectedSha256) {
        Write-Host "[Darkstar Harness] Using verified cached $Name."
        return $Cached
    }

    Remove-Item -LiteralPath $Cached -Force -ErrorAction SilentlyContinue
    $Partial = "$Cached.partial-$PID"
    Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
    Write-Host "[Darkstar Harness] Downloading pinned $Name..."
    try {
        Invoke-DarkstarDownload $Url $Partial
        $Actual = (Get-FileHash -LiteralPath $Partial -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Actual -ne $ExpectedSha256) {
            throw "SHA-256 mismatch for $Name. Expected $ExpectedSha256 but received $Actual. The file will not be installed."
        }
        Move-Item -LiteralPath $Partial -Destination $Cached -Force
        return $Cached
    } catch {
        Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
        throw
    }
}

function Get-LlamaBackendValidationIssues([string]$Directory, [string]$BackendName) {
    $Issues = [System.Collections.Generic.List[string]]::new()
    try {
        foreach ($Relative in $CommonRequiredFiles) {
            $Path = Join-Path $Directory $Relative
            if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
                $Issues.Add("missing $Relative")
                continue
            }
            if ((Get-Item -LiteralPath $Path).Length -le 0) { $Issues.Add("empty $Relative") }
        }

        $CpuBackend = Get-ChildItem -LiteralPath $Directory -Filter 'ggml-cpu*.dll' -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 0 } | Select-Object -First 1
        if (-not $CpuBackend) { $Issues.Add('missing non-empty ggml-cpu*.dll') }

        if ($BackendName -eq 'vulkan') {
            foreach ($Relative in $RequiredVulkanFiles) {
                $Path = Join-Path $Directory $Relative
                if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { $Issues.Add("missing $Relative"); continue }
                if ((Get-Item -LiteralPath $Path).Length -le 0) { $Issues.Add("empty $Relative") }
            }
        }
        if ($BackendName -eq 'cuda') {
            foreach ($Relative in $RequiredCudaFiles) {
                $Path = Join-Path $Directory $Relative
                if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { $Issues.Add("missing $Relative"); continue }
                if ((Get-Item -LiteralPath $Path).Length -le 0) { $Issues.Add("empty $Relative") }
            }
        }
    } catch {
        $Issues.Add("validation error: $($_.Exception.Message)")
    }
    return @($Issues)
}

function Test-LlamaBackend([string]$Directory, [string]$BackendName) {
    return @(Get-LlamaBackendValidationIssues $Directory $BackendName).Count -eq 0
}

function Test-AllBackends([string]$BackendsRoot, [string]$NoticeRoot) {
    foreach ($BackendName in $BackendOrder) {
        if (-not (Test-LlamaBackend (Join-Path $BackendsRoot $BackendName) $BackendName)) { return $false }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $NoticeRoot 'llama.cpp-LICENSE') -PathType Leaf)) { return $false }
    if (-not (Test-Path -LiteralPath (Join-Path $NoticeRoot 'NVIDIA-CUDA-12.4-EULA.pdf') -PathType Leaf)) { return $false }
    return $true
}

if (Test-AllBackends $BackendsDestination (Join-Path $Destination 'licenses')) {
    try {
        if (Test-Path -LiteralPath $ReceiptPath -PathType Leaf) {
            $Receipt = Get-Content -LiteralPath $ReceiptPath -Raw | ConvertFrom-Json
            $ReceiptBackends = @($Receipt.backends | ForEach-Object { [string]$_ })
            $ReceiptBackendKey = $ReceiptBackends -join ','
            if ([int]$Receipt.schemaVersion -eq $BundleVersion -and [string]$Receipt.build -eq $LlamaBuild -and [string]$Receipt.commit -eq $LlamaCommit -and [string]$Receipt.cudaRelease -eq $CudaRelease -and $ReceiptBackendKey -eq ($BackendOrder -join ',')) {
                Write-Host "[Darkstar Harness] llama.cpp $LlamaBuild CPU + Vulkan + CUDA $CudaRelease backends are ready."
                exit 0
            }
        }
    } catch {
        # A malformed receipt is treated as an incomplete managed bundle and rebuilt.
    }
}

$LlamaLicenseAsset = $NoticeDownloads | Where-Object { [string]$_.asset -eq 'llama.cpp-LICENSE' } | Select-Object -First 1
$NvidiaEulaAsset = $NoticeDownloads | Where-Object { [string]$_.asset -eq 'NVIDIA-CUDA-12.4-EULA.pdf' } | Select-Object -First 1
if ($null -eq $LlamaLicenseAsset -or $null -eq $NvidiaEulaAsset) { throw 'Pinned llama.cpp/CUDA notice metadata is incomplete.' }
$LlamaLicenseDownload = Get-VerifiedDownload $LlamaLicenseAsset @('raw.githubusercontent.com')
$EulaDownload = Get-VerifiedDownload $NvidiaEulaAsset @('docs.nvidia.com')

$Staging = Join-Path $StagingParent ("llama-all-$PID-" + [Guid]::NewGuid().ToString('N'))
$StagingBackends = Join-Path $Staging 'backends'
$StagingLicenses = Join-Path $Staging 'licenses'
New-Item -ItemType Directory -Force -Path $StagingBackends | Out-Null
New-Item -ItemType Directory -Force -Path $StagingLicenses | Out-Null

$ReceiptAssets = @()
try {
    foreach ($BackendName in $BackendOrder) {
        $BackendDirectory = Join-Path $StagingBackends $BackendName
        New-Item -ItemType Directory -Force -Path $BackendDirectory | Out-Null
        $Pin = $BackendPins.$BackendName
        Write-Host "[Darkstar Harness] Preparing llama.cpp $LlamaBuild $([string]$Pin.label) backend..."
        foreach ($Asset in @($Pin.archives)) {
            $Archive = Get-VerifiedDownload $Asset @('github.com')
            Expand-Archive -LiteralPath $Archive -DestinationPath $BackendDirectory -Force
            $ReceiptAssets += [ordered]@{
                backend = $BackendName
                asset = [string]$Asset.asset
                source = [string]$Asset.url
                sha256 = [string]$Asset.sha256
            }
        }
        $ValidationIssues = @(Get-LlamaBackendValidationIssues $BackendDirectory $BackendName)
        if ($ValidationIssues.Count -gt 0) {
            $IssueText = $ValidationIssues -join '; '
            $ExtractedNames = @(Get-ChildItem -LiteralPath $BackendDirectory -File -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -ExpandProperty Name) -join ', '
            throw "The verified llama.cpp $BackendName release archive(s) extracted, but runtime validation failed: $IssueText. Extracted files: $ExtractedNames"
        }
    }

    Copy-Item -LiteralPath $LlamaLicenseDownload -Destination (Join-Path $StagingLicenses 'llama.cpp-LICENSE') -Force
    Copy-Item -LiteralPath $EulaDownload -Destination (Join-Path $StagingLicenses 'NVIDIA-CUDA-12.4-EULA.pdf') -Force

    $LicenseReadme = Join-Path $Destination 'licenses\README.md'
    if (Test-Path -LiteralPath $LicenseReadme -PathType Leaf) {
        Copy-Item -LiteralPath $LicenseReadme -Destination (Join-Path $StagingLicenses 'README.md') -Force
    }

    if (-not (Test-AllBackends $StagingBackends $StagingLicenses)) {
        throw 'The verified all-backend llama.cpp bundle failed final staging validation.'
    }

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $BackendsBackup = "$BackendsDestination.bootstrap-backup-$PID"
    if (Test-Path -LiteralPath $BackendsBackup) { Remove-Item -LiteralPath $BackendsBackup -Recurse -Force }
    if (Test-Path -LiteralPath $BackendsDestination) { Move-Item -LiteralPath $BackendsDestination -Destination $BackendsBackup }
    try {
        Move-Item -LiteralPath $StagingBackends -Destination $BackendsDestination
        New-Item -ItemType Directory -Force -Path (Join-Path $Destination 'licenses') | Out-Null
        Copy-Item -LiteralPath (Join-Path $StagingLicenses 'llama.cpp-LICENSE') -Destination (Join-Path $Destination 'licenses\llama.cpp-LICENSE') -Force
        Copy-Item -LiteralPath (Join-Path $StagingLicenses 'NVIDIA-CUDA-12.4-EULA.pdf') -Destination (Join-Path $Destination 'licenses\NVIDIA-CUDA-12.4-EULA.pdf') -Force
        if (Test-Path -LiteralPath (Join-Path $StagingLicenses 'README.md') -PathType Leaf) {
            Copy-Item -LiteralPath (Join-Path $StagingLicenses 'README.md') -Destination (Join-Path $Destination 'licenses\README.md') -Force
        }

        $Receipt = [ordered]@{
            schemaVersion = $BundleVersion
            build = $LlamaBuild
            commit = $LlamaCommit
            cudaRelease = $CudaRelease
            backends = @($BackendOrder)
            assets = $ReceiptAssets
            notices = @($NoticeDownloads | ForEach-Object { [ordered]@{ asset = $_.asset; source = $_.url; sha256 = $_.sha256 } })
            installedAtUtc = [DateTime]::UtcNow.ToString('o')
        }
        $Receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8

        if (-not (Test-AllBackends $BackendsDestination (Join-Path $Destination 'licenses'))) {
            throw 'llama.cpp all-backend installation completed but final runtime validation failed.'
        }
        if (Test-Path -LiteralPath $BackendsBackup) { Remove-Item -LiteralPath $BackendsBackup -Recurse -Force }
    } catch {
        if (Test-Path -LiteralPath $BackendsDestination) { Remove-Item -LiteralPath $BackendsDestination -Recurse -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $BackendsBackup) { Move-Item -LiteralPath $BackendsBackup -Destination $BackendsDestination }
        throw
    }
} finally {
    if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue }
}

Write-Host "[Darkstar Harness] llama.cpp $LlamaBuild CPU + Vulkan + CUDA $CudaRelease backends installed and verified."
