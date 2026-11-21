param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,
    [Parameter(Mandatory = $true)]
    [string]$Python
)

$ErrorActionPreference = "Stop"
$backend = Join-Path $Repo "backend"
$root = Join-Path $Repo "experiments\docvqa"
$logDir = Join-Path $Repo "storage-smoke\w3-logs"
$consoleLog = Join-Path $logDir "experiments.txt"
$resultFile = Join-Path $logDir "experiment-exits.json"
$configs = @(
    "B0",
    "B1",
    "B2",
    "B3",
    "B3-no-ocr",
    "B3-no-clip",
    "clip-only",
    "B3-k10",
    "B3-k30",
    "B3-k100"
)

$baseConfig = Join-Path $Repo "experiments\configs"
$results = @()
Set-Location $backend

foreach ($name in $configs) {
    $config = Join-Path $baseConfig "$name.json"
    $started = Get-Date
    $output = & $Python -m app.modules.experiments `
        --root $root run --config $config --repeat 3 2>&1
    $code = $LASTEXITCODE
    $finished = Get-Date
    $output | ForEach-Object {
        "[$name] $_" | Tee-Object -FilePath $consoleLog -Append
    } | Out-Null
    $runDir = Get-ChildItem -LiteralPath (Join-Path $root "runs") -Directory |
        Where-Object { $_.Name -match "_$([regex]::Escape($name))_[0-9a-f]{6}$" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    $results += [pscustomobject]@{
        config = $name
        exit_code = $code
        started_at = $started.ToString("o")
        finished_at = $finished.ToString("o")
        elapsed_seconds = [math]::Round(($finished - $started).TotalSeconds, 3)
        run_dir = if ($runDir) { $runDir.Name } else { $null }
    }
    $results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $resultFile -Encoding UTF8
    if ($code -ne 0) {
        Write-Output "[$name] exit code $code; continuing so every configuration gets a raw result"
    }
}

$results | Format-Table -AutoSize
if (($results | Where-Object { $_.exit_code -ne 0 }).Count -gt 0) {
    exit 1
}
