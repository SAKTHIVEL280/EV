<#
.SYNOPSIS
  Spike S3: measure the pinned llama.cpp build (CPU and Vulkan) on this Windows PC.

.DESCRIPTION
  Downloads the llama.cpp builds pinned in llama-cpp.pins (SHA-256 verified),
  runs llama-bench for prompt processing (512 tokens) and generation (128
  tokens), and measures llama-server memory with `-lm none` and with the default
  load mode. Writes one JSON file with system info and results.

  Run (from the folder containing this script):
    powershell -ExecutionPolicy Bypass -File .\s3-llama.ps1 -ModelPath C:\path\Qwen3.5-4B-Q4_K_M.gguf

.PARAMETER ModelPath
  Qwen3.5-4B Q4_K_M GGUF file.

.PARAMETER Threads
  CPU threads. Default 8 matches the Linux baseline in docs/PERFORMANCE.md.

.PARAMETER OutDir
  Results folder. Default: Desktop\ev-spike-results.
#>
param(
  [Parameter(Mandatory = $true)][string]$ModelPath,
  [int]$Threads = 8,
  [string]$OutDir = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ev-spike-results')
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'
# Invoke-WebRequest is extremely slow in Windows PowerShell 5.1 with the progress bar.
$ProgressPreference = 'SilentlyContinue'

if (-not (Test-Path -LiteralPath $ModelPath)) { throw "Model not found: $ModelPath" }
$ModelPath = (Resolve-Path -LiteralPath $ModelPath).Path
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Work = Join-Path $env:TEMP 'ev-s3'
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Get-LlamaBuild {
  param([string]$Tag, [string]$Variant, [string]$Sha)
  $zip = "llama-$Tag-bin-$Variant.zip"
  $zipPath = Join-Path $Work $zip
  $dir = Join-Path $Work "$Tag-$Variant"
  if (-not (Test-Path -LiteralPath (Join-Path $dir 'llama-server.exe'))) {
    $url = "https://github.com/ggml-org/llama.cpp/releases/download/$Tag/$zip"
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
    if ($actual -ne $Sha) { throw "SHA-256 mismatch for $zip (expected $Sha, got $actual)" }
    if (Test-Path -LiteralPath $dir) { Remove-Item -Recurse -Force -LiteralPath $dir }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $dir
  }
  return $dir
}

function Invoke-Native {
  # Runs a native program with stdout/stderr redirected to files; returns exit code and stdout.
  param([string]$Exe, [string]$Arguments, [string]$LogName)
  $out = Join-Path $OutDir "$Stamp-$LogName.out.txt"
  $err = Join-Path $OutDir "$Stamp-$LogName.err.txt"
  $p = Start-Process -FilePath $Exe -ArgumentList $Arguments -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $out -RedirectStandardError $err
  return @{ exit = $p.ExitCode; stdout = (Get-Content -Raw -LiteralPath $out) }
}

function Invoke-Bench {
  param([string]$Dir, [string]$Extra, [string]$Label)
  Write-Host "llama-bench: $Label"
  $arguments = "-m `"$ModelPath`" -p 512 -n 128 -t $Threads -r 3 -lm none -o json $Extra"
  $r = Invoke-Native -Exe (Join-Path $Dir 'llama-bench.exe') -Arguments $arguments -LogName "bench-$Label"
  if ($r.exit -ne 0) { return @{ label = $Label; error = "llama-bench exit code $($r.exit)" } }
  $rows = $r.stdout | ConvertFrom-Json
  $result = @{ label = $Label; args = $arguments }
  foreach ($row in $rows) {
    if ($row.n_prompt -gt 0) { $result.prompt_tok_s = [math]::Round($row.avg_ts, 1) }
    if ($row.n_gen -gt 0) { $result.generate_tok_s = [math]::Round($row.avg_ts, 1) }
    $result.backends = $row.backends
  }
  return $result
}

function Measure-Server {
  param([string]$Dir, [string]$Extra, [string]$Label)
  Write-Host "llama-server memory: $Label"
  $port = Get-Random -Minimum 20000 -Maximum 40000
  $arguments = "-m `"$ModelPath`" --host 127.0.0.1 --port $port -t $Threads -c 8192 $Extra"
  $p = Start-Process -FilePath (Join-Path $Dir 'llama-server.exe') -ArgumentList $arguments -NoNewWindow -PassThru `
    -RedirectStandardOutput (Join-Path $OutDir "$Stamp-server-$Label.out.txt") `
    -RedirectStandardError (Join-Path $OutDir "$Stamp-server-$Label.err.txt")
  try {
    $deadline = (Get-Date).AddMinutes(5)
    $ready = $false
    while ((Get-Date) -lt $deadline -and -not $p.HasExited) {
      try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 2
        if ($health.StatusCode -eq 200) { $ready = $true; break }
      } catch {
        # 503 while the model loads, or connection refused before bind.
      }
      Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { return @{ label = $Label; args = $arguments; error = 'server did not become ready' } }
    # One short completion so compute buffers are allocated before measuring.
    $body = @{ prompt = 'Hello'; n_predict = 8 } | ConvertTo-Json
    Invoke-WebRequest -Uri "http://127.0.0.1:$port/completion" -Method Post -Body $body `
      -ContentType 'application/json' -UseBasicParsing -TimeoutSec 300 | Out-Null
    Start-Sleep -Seconds 2
    $p.Refresh()
    return @{
      label = $Label
      args = $arguments
      working_set_mb = [math]::Round($p.WorkingSet64 / 1MB)
      private_mb = [math]::Round($p.PrivateMemorySize64 / 1MB)
      peak_working_set_mb = [math]::Round($p.PeakWorkingSet64 / 1MB)
    }
  } finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
  }
}

$pins = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'llama-cpp.pins') |
  Where-Object { $_.Trim() -and -not $_.StartsWith('#') }
$builds = @{}
foreach ($line in $pins) {
  $parts = $line.Trim() -split '\s+'
  $builds[$parts[1]] = @{ tag = $parts[0]; dir = (Get-LlamaBuild -Tag $parts[0] -Variant $parts[1] -Sha $parts[2]) }
}
$cpu = $builds['win-cpu-x64']
$vulkan = $builds['win-vulkan-x64']

$proc = Get-CimInstance Win32_Processor
$os = Get-CimInstance Win32_OperatingSystem
Write-Host 'Hashing model (this takes a few seconds)'
$system = @{
  cpu = (@($proc)[0].Name).Trim()
  physical_cores = ($proc | Measure-Object -Property NumberOfCores -Sum).Sum
  logical_processors = [Environment]::ProcessorCount
  ram_gb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
  gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object { "$($_.Name) (driver $($_.DriverVersion))" })
  os = "$($os.Caption) build $($os.BuildNumber)"
  on_battery = [bool](@(Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Where-Object { $_.BatteryStatus -eq 1 }).Count)
  model_file = (Split-Path -Leaf $ModelPath)
  model_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ModelPath).Hash.ToLowerInvariant()
  threads = $Threads
}

$devices = Invoke-Native -Exe (Join-Path $vulkan.dir 'llama-server.exe') -Arguments '--list-devices' -LogName 'vulkan-devices'

$results = [ordered]@{
  spike = 'S3'
  date = (Get-Date).ToString('o')
  llama_cpp = $cpu.tag
  system = $system
  vulkan_devices = $devices.stdout
  bench = @(
    (Invoke-Bench -Dir $cpu.dir -Extra '' -Label 'cpu'),
    (Invoke-Bench -Dir $vulkan.dir -Extra '-ngl 99' -Label 'vulkan-ngl99')
  )
  server_memory = @(
    (Measure-Server -Dir $cpu.dir -Extra '-lm none' -Label 'cpu-lm-none'),
    (Measure-Server -Dir $cpu.dir -Extra '' -Label 'cpu-default-load'),
    (Measure-Server -Dir $vulkan.dir -Extra '-ngl 99 -lm none' -Label 'vulkan-ngl99-lm-none')
  )
}

$file = Join-Path $OutDir "s3-$Stamp.json"
$results | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $file -Encoding UTF8
Write-Host ''
Write-Host 'Benchmarks (tokens/s)'
$results.bench | ForEach-Object { [pscustomobject]$_ } | Format-Table label, prompt_tok_s, generate_tok_s, error -AutoSize
Write-Host 'llama-server memory (MB)'
$results.server_memory | ForEach-Object { [pscustomobject]$_ } | Format-Table label, working_set_mb, private_mb, peak_working_set_mb, error -AutoSize
Write-Host "Saved $file"
