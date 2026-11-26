param(
    [Parameter(Mandatory = $true)]
    [string]$StopFile,
    [Parameter(Mandatory = $true)]
    [string]$OutputFile
)

$ErrorActionPreference = "Stop"
$header = "timestamp,api_mb,clip_mb,worker_mb,ocr_mb,system_available_mb"
$header | Set-Content -LiteralPath $OutputFile -Encoding UTF8

$groupPids = @{
    api = @()
    clip = @()
    worker = @()
    ocr = @()
}
$refreshCounter = 1000
$deadline = (Get-Date).AddHours(1)

function Refresh-Groups {
    $processes = @(Get-CimInstance Win32_Process)
    $byId = @{}
    $children = @{}
    foreach ($process in $processes) {
        $processId = [int]$process.ProcessId
        $byId[$processId] = $process
        $parent = [int]$process.ParentProcessId
        if (-not $children.ContainsKey($parent)) {
            $children[$parent] = [System.Collections.Generic.List[int]]::new()
        }
        $children[$parent].Add($processId)
    }

    foreach ($group in @("api", "clip", "worker", "ocr")) {
        $pattern = switch ($group) {
            "api" { "uvicorn\s+app\.main:create_app" }
            "clip" { "-m\s+clip_service" }
            "worker" { "-m\s+app\.worker" }
            "ocr" { "-m\s+ocr_worker" }
        }
        $roots = @(
            $processes |
                Where-Object { $_.CommandLine -and $_.CommandLine -match $pattern } |
                ForEach-Object { [int]$_.ProcessId }
        )
        $selected = [System.Collections.Generic.HashSet[int]]::new()
        $queue = [System.Collections.Generic.Queue[int]]::new()
        foreach ($root in $roots) { $queue.Enqueue($root) }
        while ($queue.Count -gt 0) {
            $current = $queue.Dequeue()
            if (-not $selected.Add($current)) { continue }
            if ($children.ContainsKey($current)) {
                foreach ($child in $children[$current]) { $queue.Enqueue($child) }
            }
        }
        $groupPids[$group] = @($selected)
    }
}

while (-not (Test-Path -LiteralPath $StopFile) -and (Get-Date) -lt $deadline) {
    if ($refreshCounter -ge 10) {
        Refresh-Groups
        $refreshCounter = 0
    }
    $refreshCounter += 1

    $values = @{}
    foreach ($group in @("api", "clip", "worker", "ocr")) {
        $bytes = 0L
        foreach ($processId in $groupPids[$group]) {
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process) { $bytes += $process.WorkingSet64 }
        }
        $values[$group] = [math]::Round($bytes / 1MB, 1)
    }

    $available = [math]::Round(
        (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024,
        1
    )
    $timestamp = (Get-Date).ToString("o")
    "$timestamp,$($values.api),$($values.clip),$($values.worker),$($values.ocr),$available" |
        Add-Content -LiteralPath $OutputFile -Encoding UTF8
    Start-Sleep -Milliseconds 900
}
