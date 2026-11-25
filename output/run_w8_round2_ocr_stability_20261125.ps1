$ErrorActionPreference = "Stop"

$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path
$root = "C:\Users\lenovo\Desktop\my-software-main\_gh_upload"
$dataset = "C:\Users\lenovo\Desktop\my-software-main\w8-data\docvqa-crash4"
$out = Join-Path $root "output\w8-round2f-20261125"
$storage = Join-Path $root "storage\w8-round2c-20261125"
$runtime = Join-Path $out "runtime"
New-Item -ItemType Directory -Path $runtime -Force | Out-Null

foreach ($line in Get-Content -LiteralPath (Join-Path $root ".env") -Encoding UTF8) {
    if ($line -match "^([^#=]+)=(.*)$") {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

$env:PYTHONPATH = $root
$env:DATABASE_URL = "postgresql://REDACTED:REDACTED@127.0.0.1:55433/docmgr_w8_round2c_20261125"
$env:OPENSEARCH_URL = "http://127.0.0.1:9201"
$env:OPENSEARCH_INDEX_PREFIX = "w8r2c_"
$env:STORAGE_ROOT = $storage
$env:CLIP_SERVICE_URL = "http://127.0.0.1:8001"
$env:CLIP_MODEL_PATH = Join-Path $root "models\clip\clip_cn_vit-b-16.pt"
$env:OCR_DET_MODEL_DIR = Join-Path $root "models\ocr\PP-OCRv5_mobile_det"
$env:OCR_REC_MODEL_DIR = Join-Path $root "models\ocr\PP-OCRv5_mobile_rec"
$env:OCR_WORKER_POLL_SECONDS = "1"

$main = Join-Path $root ".venv-main\Scripts\python.exe"
$ocrPython = Join-Path $root "env_check\.venv-ocr\Scripts\python.exe"
$backend = Join-Path $root "backend"
$ocrDir = Join-Path $root "services\ocr_worker"
$db = "docmgr_w8_round2c_20261125"

function Invoke-DbScalar {
    param([string]$Sql)
    return ((& docker exec docmgr-postgres-1 psql -U docmgr -d $db -Atc $Sql) -join "").Trim()
}

function Wait-Tasks {
    param(
        [string]$Where,
        [int]$ExpectedSucceeded,
        [int]$TimeoutSeconds
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $pending = [int](Invoke-DbScalar "select count(*) from processing_tasks where $Where and status in ('pending','processing')")
        $failed = [int](Invoke-DbScalar "select count(*) from processing_tasks where $Where and status='failed'")
        $succeeded = [int](Invoke-DbScalar "select count(*) from processing_tasks where $Where and status='succeeded'")
        if ($pending -eq 0 -and ($succeeded + $failed) -ge $ExpectedSucceeded) {
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for tasks: $Where; pending=$pending failed=$failed succeeded=$succeeded"
}

function Stop-ProcessTree {
    param([int[]]$RootIds)
    $processes = @(Get-CimInstance Win32_Process)
    $all = [System.Collections.Generic.HashSet[int]]::new()
    $queue = [System.Collections.Generic.Queue[int]]::new()
    foreach ($id in $RootIds) { $queue.Enqueue($id) }
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        if (-not $all.Add($current)) { continue }
        foreach ($child in $processes | Where-Object { $_.ParentProcessId -eq $current }) {
            $queue.Enqueue([int]$child.ProcessId)
        }
    }
    foreach ($id in $all) {
        Stop-Process -Id $id -ErrorAction SilentlyContinue
    }
}

$monitorScript = Join-Path $root "output\monitor_w8_fast_20261125.ps1"
$stopFile = Join-Path $runtime "stop.flag"
$memoryFile = Join-Path $runtime "memory.csv"
if (Test-Path $stopFile) {
    throw "Stop file already exists; refusing to overwrite prior test state: $stopFile"
}

$monitor = Start-Process `
    -FilePath (Get-Process -Id $PID).Path `
    -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $monitorScript,
        "-StopFile",
        $stopFile,
        "-OutputFile",
        $memoryFile
    ) `
    -WindowStyle Hidden `
    -PassThru

$genericWorkers = @()
try {
    $genericWorkers += Start-Process `
        -FilePath $main `
        -ArgumentList @("-m", "app.worker") `
        -WorkingDirectory $backend `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtime "generic-worker.out.log") `
        -RedirectStandardError (Join-Path $runtime "generic-worker.err.log") `
        -PassThru
    Wait-Tasks -Where "task_type in ('parse','embed')" -ExpectedSucceeded 8 -TimeoutSeconds 120
}
finally {
    if ($genericWorkers.Count -gt 0) {
        Stop-ProcessTree -RootIds @($genericWorkers.ProcessId)
    }
}

$rounds = @()
foreach ($mode in @("single", "multi4")) {
    $firstRound = if ($mode -eq "single") { 11 } else { 3 }
    for ($round = $firstRound; $round -le 10; $round++) {
        $started = Get-Date
        Push-Location $backend
        try {
            & $main -m app.modules.experiments --root $dataset reocr --yes 2>&1 |
                Tee-Object -FilePath (Join-Path $out "$mode-round$round-reocr.txt")
            $reocrExit = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
        if ($reocrExit -ne 0) { throw "reocr failed for $mode round $round" }
        Start-Sleep -Seconds 2

        $workers = @()
        if ($mode -eq "single") {
            $workers = @(
                Start-Process `
                    -FilePath $ocrPython `
                    -ArgumentList @("-m", "ocr_worker") `
                    -WorkingDirectory $ocrDir `
                    -WindowStyle Hidden `
                    -RedirectStandardOutput (Join-Path $runtime "$mode-$round.out.log") `
                    -RedirectStandardError (Join-Path $runtime "$mode-$round.err.log") `
                    -PassThru
            )
        }
        else {
            $workers = @(
                1..4 | ForEach-Object {
                    Start-Process `
                        -FilePath $ocrPython `
                        -ArgumentList @("-m", "ocr_worker") `
                        -WorkingDirectory $ocrDir `
                        -WindowStyle Hidden `
                        -RedirectStandardOutput (Join-Path $runtime "$mode-$round-worker$_.out.log") `
                        -RedirectStandardError (Join-Path $runtime "$mode-$round-worker$_.err.log") `
                        -PassThru
                }
            )
        }

        Wait-Tasks -Where "task_type='ocr'" -ExpectedSucceeded 4 -TimeoutSeconds 600
        $finished = Get-Date

        $csv = Join-Path $out "$mode-r$('{0:D2}' -f $round).csv"
        & docker exec docmgr-postgres-1 psql -U docmgr -d $db -c "\copy (select task_type,document_id,status,attempts,max_attempts,error,started_at,finished_at from processing_tasks where task_type='ocr' order by document_id) to stdout with csv header" |
            Set-Content -LiteralPath $csv -Encoding UTF8

        $succeeded = [int](Invoke-DbScalar "select count(*) from processing_tasks where task_type='ocr' and status='succeeded'")
        $failed = [int](Invoke-DbScalar "select count(*) from processing_tasks where task_type='ocr' and status='failed'")
        $attemptsGt1 = [int](Invoke-DbScalar "select count(*) from processing_tasks where task_type='ocr' and attempts>1")
        $rounds += [PSCustomObject]@{
            mode = $mode
            round = $round
            started = $started.ToString("o")
            finished = $finished.ToString("o")
            elapsed_seconds = [math]::Round(($finished - $started).TotalSeconds, 3)
            succeeded = $succeeded
            failed = $failed
            attempts_gt1 = $attemptsGt1
            worker_pids = @($workers.ProcessId)
        }
        Stop-ProcessTree -RootIds @($workers.ProcessId)
    }
}

New-Item -ItemType File -Path $stopFile -Force | Out-Null
Start-Sleep -Seconds 4
if (-not $monitor.HasExited) {
    Stop-Process -Id $monitor.Id -ErrorAction SilentlyContinue
}

$memory = if (Test-Path $memoryFile) {
    $samples = Import-Csv -LiteralPath $memoryFile | ForEach-Object {
        [PSCustomObject]@{
            timestamp = [datetimeoffset]$_.timestamp
            api_mb = [double]$_.api_mb
            clip_mb = [double]$_.clip_mb
            worker_mb = [double]$_.worker_mb
            ocr_mb = [double]$_.ocr_mb
            system_available_mb = [double]$_.system_available_mb
        }
    }
    $ordered = @($samples | Where-Object timestamp | Sort-Object timestamp)
    $gaps = for ($i = 1; $i -lt $ordered.Count; $i++) {
        ($ordered[$i].timestamp - $ordered[$i - 1].timestamp).TotalSeconds
    }
    @{
        samples = $ordered.Count
        start = if ($ordered.Count) { $ordered[0].timestamp.ToString("o") } else { $null }
        end = if ($ordered.Count) { $ordered[-1].timestamp.ToString("o") } else { $null }
        min_gap_s = if ($gaps.Count) { [math]::Round(($gaps | Measure-Object -Minimum).Minimum, 3) } else { $null }
        max_gap_s = if ($gaps.Count) { [math]::Round(($gaps | Measure-Object -Maximum).Maximum, 3) } else { $null }
        peak_api_mb = ($ordered.api_mb | Measure-Object -Maximum).Maximum
        peak_clip_mb = ($ordered.clip_mb | Measure-Object -Maximum).Maximum
        peak_worker_mb = ($ordered.worker_mb | Measure-Object -Maximum).Maximum
        peak_ocr_mb = ($ordered.ocr_mb | Measure-Object -Maximum).Maximum
        minimum_system_available_mb = ($ordered.system_available_mb | Measure-Object -Minimum).Minimum
    }
}
else {
    @{ samples = 0 }
}

$summary = @{
    generated_at = (Get-Date).ToString("o")
    rounds = $rounds
    memory = $memory
}
$summary | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $out "summary.json") -Encoding UTF8
$summary | ConvertTo-Json -Depth 8
