<#
.SYNOPSIS
  Zip EV's logs and the spike results so they can be shared for docs/PERFORMANCE.md.

.DESCRIPTION
  Collects %APPDATA%\EV\logs (app.log, core.log; no conversation content is
  logged at INFO) and Desktop\ev-spike-results into Desktop\ev-spike-results.zip.

  Run: powershell -ExecutionPolicy Bypass -File .\collect-results.ps1
#>
Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'

$desktop = [Environment]::GetFolderPath('Desktop')
$staging = Join-Path $env:TEMP ("ev-results-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path $staging | Out-Null

$logs = Join-Path $env:APPDATA 'EV\logs'
if (Test-Path -LiteralPath $logs) { Copy-Item -Recurse -LiteralPath $logs -Destination (Join-Path $staging 'logs') }
else { Write-Host "No EV logs found at $logs" }

$spike = Join-Path $desktop 'ev-spike-results'
if (Test-Path -LiteralPath $spike) { Copy-Item -Recurse -LiteralPath $spike -Destination (Join-Path $staging 'spike-results') }

$zip = Join-Path $desktop 'ev-spike-results.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -Force -LiteralPath $zip }
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zip
Remove-Item -Recurse -Force -LiteralPath $staging
Write-Host "Saved $zip"
