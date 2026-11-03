#requires -Version 5.1
<#
Downloads a pinned official AstrBot Desktop installer, checks its SHA256,
and opens the normal installation UI. Does not configure accounts or services.
Use -DownloadOnly to prepare the verified installer without running it.
#>
[CmdletBinding()]
param([switch]$DownloadOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') { throw 'Run this helper on Windows.' }
if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is unavailable.' }

$machineArch = [Environment]::GetEnvironmentVariable('PROCESSOR_ARCHITECTURE', 'Machine')
if (-not $machineArch) { $machineArch = $env:PROCESSOR_ARCHITECTURE }
$version = '4.29.4'
switch ($machineArch.ToUpperInvariant()) {
    'AMD64' {
        $asset = 'AstrBot_4.29.4_windows_amd64_setup.exe'
        $expected = '7c65c03a9d6ed838a4f3ece11f7a88e44a81d0cfcb92094d1ebe14941938e1a6'
    }
    'ARM64' {
        $asset = 'AstrBot_4.29.4_windows_arm64_setup.exe'
        $expected = '1da76d3fdaa980e57e89b32f9c532424707bb5cbbfda5b0ab571399b8fb781d3'
    }
    default { throw "Unsupported architecture: $machineArch. Use the official release page." }
}

$installDir = Join-Path $env:LOCALAPPDATA 'SecondBrain\installers'
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
$installer = Join-Path $installDir $asset
$url = "https://github.com/AstrBotDevs/AstrBot-desktop/releases/download/v$version/$asset"

$cachedValid = $false
if (Test-Path -LiteralPath $installer -PathType Leaf) {
    $cachedValid = ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -eq $expected)
}
if (-not $cachedValid) {
    Write-Host "Downloading official AstrBot Desktop $version ($machineArch)..."
    $partial = "$installer.partial"
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    try {
        Invoke-WebRequest -Uri $url -OutFile $partial -UseBasicParsing -TimeoutSec 300
        $actual = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash
        if ($actual -ne $expected) { throw 'SHA256 mismatch. The installer will not be executed.' }
        Move-Item -LiteralPath $partial -Destination $installer -Force
    }
    finally {
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    }
}
Write-Host "Verified installer: $installer"
if ($DownloadOnly) { return }
Write-Host 'Opening the normal installer. Finish its on-screen steps; no account is configured by this helper.'
$process = Start-Process -FilePath $installer -PassThru -Wait
if ($process.ExitCode -notin @(0, 3010)) {
    throw "Installer exited with code $($process.ExitCode). Check the installation UI."
}
Write-Host 'Installer exited. Open AstrBot and verify that its main window loads.'
Write-Host 'QQ, AI processing, file archiving and phone push are NOT connected yet.'
