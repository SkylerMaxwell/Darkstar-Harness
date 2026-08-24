# SPDX-License-Identifier: GPL-3.0-only
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$launcherDir = Join-Path $root 'launcher\windows'
$output = Join-Path $root 'Darkstar.exe'

$go = Get-Command go.exe -ErrorAction SilentlyContinue
if (-not $go) {
    $go = Get-Command go -ErrorAction SilentlyContinue
}
if (-not $go) {
    throw 'Go is required to rebuild Darkstar.exe. Install Go 1.22 or newer and retry.'
}

Push-Location $launcherDir
try {
    & $go.Source test .
    if ($LASTEXITCODE -ne 0) { throw 'Darkstar.exe launcher tests failed.' }

    $previousGoos = $env:GOOS
    $previousGoarch = $env:GOARCH
    $previousCgo = $env:CGO_ENABLED
    try {
        $env:GOOS = 'windows'
        $env:GOARCH = 'amd64'
        $env:CGO_ENABLED = '0'
        & $go.Source build -trimpath '-ldflags=-H=windowsgui -s -w -buildid=' -o $output .
        if ($LASTEXITCODE -ne 0) { throw 'Darkstar.exe build failed.' }
    } finally {
        $env:GOOS = $previousGoos
        $env:GOARCH = $previousGoarch
        $env:CGO_ENABLED = $previousCgo
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
    throw 'Darkstar.exe was not produced.'
}
Write-Host "[Darkstar Harness] Built $output"
