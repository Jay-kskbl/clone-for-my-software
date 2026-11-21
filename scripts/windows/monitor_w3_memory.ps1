param(
    [Parameter(Mandatory = $true)]
    [string]$StopFile,
    [Parameter(Mandatory = $true)]
    [string]$OutputFile
)

$ErrorActionPreference = "Stop"
$peaks = @{
    api_mb = 0.0
    clip_mb = 0.0
    worker_mb = 0.0
    ocr_mb = 0.0
}

function Get-ServiceWorkingSetMB {
    param(
        [object[]]$Processes,
        [string]$CommandPattern
    )

    $byId = @{}
    $children = @{}
    foreach ($process in $Processes) {
        $byId[[int]$process.ProcessId] = $process
        $parent = [int]$process.ParentProcessId
        if (-not $children.ContainsKey($parent)) {
            $children[$parent] = [System.Collections.Generic.List[int]]::new()
        }
        $children[$parent].Add([int]$process.ProcessId)
    }

    $matched = @(
        $Processes | Where-Object {
            $_.CommandLine -and $_.CommandLine -match $CommandPattern
        } | ForEach-Object { [int]$_.ProcessId }
    )
    if ($matched.Count -eq 0) {
        return 0.0
    }

    $roots = @(
        $matched | Where-Object {
            $candidate = $_
            $parent = [int]$byId[$candidate].ParentProcessId
            $inside = $false
            while ($byId.ContainsKey($parent)) {
                if ($matched -contains $parent) {
                    $inside = $true
                    break
                }
                $parent = [int]$byId[$parent].ParentProcessId
            }
            -not $inside
        }
    )

    $selected = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($root in $roots) {
        $stack = [System.Collections.Generic.Stack[int]]::new()
        $stack.Push($root)
        while ($stack.Count -gt 0) {
            $current = $stack.Pop()
            if (-not $selected.Add($current)) {
                continue
            }
            if ($children.ContainsKey($current)) {
                foreach ($child in $children[$current]) {
                    $stack.Push($child)
                }
            }
        }
    }

    $bytes = 0L
    foreach ($id in $selected) {
        $bytes += [int64]$byId[$id].WorkingSetSize
    }
    return [math]::Round($bytes / 1MB, 1)
}

while (-not (Test-Path -LiteralPath $StopFile)) {
    $processes = @(Get-CimInstance Win32_Process)
    $values = @{
        api_mb = Get-ServiceWorkingSetMB $processes "uvicorn\s+app\.main:create_app"
        clip_mb = Get-ServiceWorkingSetMB $processes "-m\s+clip_service"
        worker_mb = Get-ServiceWorkingSetMB $processes "-m\s+app\.worker"
        ocr_mb = Get-ServiceWorkingSetMB $processes "-m\s+ocr_worker"
    }
    foreach ($key in @("api_mb", "clip_mb", "worker_mb", "ocr_mb")) {
        if ($values[$key] -gt $peaks[$key]) {
            $peaks[$key] = $values[$key]
        }
    }
    $peaks | ConvertTo-Json | Set-Content -LiteralPath $OutputFile -Encoding UTF8
    Start-Sleep -Seconds 3
}
