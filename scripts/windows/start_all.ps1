param(
    [int]$ReadyTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runtime = Join-Path $root ".tools\runtime"
$logs = Join-Path $runtime "logs"
$stateFile = Join-Path $runtime "processes.json"
$backendStopFile = Join-Path $runtime "backend-worker.stop"
$ocrStopFile = Join-Path $runtime "ocr-worker.stop"

$postgresHome = Join-Path $root ".tools\postgresql-16.15\pgsql"
$postgresData = Join-Path $root ".tools\postgresql-data"
$postgresCtl = Join-Path $postgresHome "bin\pg_ctl.exe"
$psql = Join-Path $postgresHome "bin\psql.exe"
$openSearchHome = Join-Path $root ".tools\opensearch-2.19.1\opensearch-2.19.1"
$openSearchBat = Join-Path $openSearchHome "bin\opensearch.bat"
$mainPython = Join-Path $root ".venv-main\Scripts\python.exe"
$ocrPython = Join-Path $root "env_check\.venv-ocr\Scripts\python.exe"
$clipPython = Join-Path $root "env_check\.venv-clip\Scripts\python.exe"
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$ocrDir = Join-Path $root "services\ocr_worker"
$clipDir = Join-Path $root "services\clip_service"
$node = (Get-Command node -ErrorAction Stop).Source
$hostExe = (Get-Process -Id $PID).Path

New-Item -ItemType Directory -Path $logs -Force | Out-Null
Remove-Item -LiteralPath $backendStopFile, $ocrStopFile -Force -ErrorAction SilentlyContinue

$env:PYTHONPATH = $root
$env:OPENSEARCH_JAVA_HOME = Join-Path $openSearchHome "jdk"

function Test-Http {
    param([string]$Uri)
    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Start-Hidden {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$LogName
    )

    return Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "$LogName.out.log") `
        -RedirectStandardError (Join-Path $logs "$LogName.err.log") `
        -PassThru
}

$saved = @{}
if (Test-Path -LiteralPath $stateFile) {
    $stored = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    foreach ($property in $stored.PSObject.Properties) {
        $saved[$property.Name] = [int]$property.Value
    }
}

function Test-SavedProcess {
    param([string]$Name)
    if (-not $saved.ContainsKey($Name)) {
        return $false
    }
    return $null -ne (Get-Process -Id $saved[$Name] -ErrorAction SilentlyContinue)
}

$started = @{}

$dbReady = $false
try {
    $dbReady = ((& $psql -h 127.0.0.1 -p 55432 -U docmgr -d docmgr -tAc "SELECT 1" 2>$null) -join "").Trim() -eq "1"
} catch {
    $dbReady = $false
}
if (-not $dbReady) {
    & $postgresCtl -D $postgresData -l (Join-Path $logs "postgres.log") `
        -o '"-p" "55432" "-h" "127.0.0.1"' start | Out-Host
}

if (-not (Test-Http "http://127.0.0.1:9200/")) {
    $started.opensearch = Start-Hidden `
        -FilePath "C:\Windows\System32\cmd.exe" `
        -Arguments @(
            "/c",
            $openSearchBat,
            "-Ediscovery.type=single-node",
            "-Enetwork.host=127.0.0.1",
            "-Ehttp.port=9200",
            "-Eplugins.security.disabled=true",
            "-Eaction.auto_create_index=false"
        ) `
        -WorkingDirectory $openSearchHome `
        -LogName "opensearch"
}

if (-not (Test-Http "http://127.0.0.1:8001/health")) {
    $started.clip = Start-Hidden `
        -FilePath $clipPython `
        -Arguments @("-m", "clip_service") `
        -WorkingDirectory $clipDir `
        -LogName "clip"
}

if (-not (Test-Http "http://127.0.0.1:8000/health")) {
    $started.backend = Start-Hidden `
        -FilePath $mainPython `
        -Arguments @("-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $backendDir `
        -LogName "backend"
}
if (-not (Test-SavedProcess "backend_worker")) {
    $started.backend_worker = Start-Hidden `
        -FilePath $hostExe `
        -Arguments @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "run_backend_worker_loop.ps1"),
            "-Python", $mainPython,
            "-StopFile", $backendStopFile
        ) `
        -WorkingDirectory $backendDir `
        -LogName "backend-worker"
}

if (-not (Test-Http "http://127.0.0.1:5173")) {
    $started.frontend = Start-Hidden `
        -FilePath $node `
        -Arguments @(
            (Join-Path $frontendDir "node_modules\vite\bin\vite.js"),
            "--host", "127.0.0.1",
            "--port", "5173"
        ) `
        -WorkingDirectory $frontendDir `
        -LogName "frontend"
}

if (-not (Test-SavedProcess "ocr_worker")) {
    $started.ocr_worker = Start-Hidden `
        -FilePath $hostExe `
        -Arguments @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "run_ocr_worker_loop.ps1"),
            "-Python", $ocrPython,
            "-StopFile", $ocrStopFile
        ) `
        -WorkingDirectory $ocrDir `
        -LogName "ocr-worker"
}

$processIds = [ordered]@{}
foreach ($name in $saved.Keys) {
    if ($null -ne (Get-Process -Id $saved[$name] -ErrorAction SilentlyContinue)) {
        $processIds[$name] = $saved[$name]
    }
}
foreach ($name in $started.Keys) {
    $processIds[$name] = $started[$name].Id
}
$processIds | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8

$deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
$health = $null
do {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3
    } catch {
        $health = $null
    }
    if ($health -and $health.status -eq "ok" -and (Test-Http "http://127.0.0.1:5173")) {
        break
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if (-not $health -or $health.status -ne "ok" -or -not (Test-Http "http://127.0.0.1:5173")) {
    throw "The stack did not become ready. Check logs in $logs."
}

Write-Host "DocMgr is running: http://127.0.0.1:5173"
$health | ConvertTo-Json -Depth 5
Write-Host "Logs: $logs"
