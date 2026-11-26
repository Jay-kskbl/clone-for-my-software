$ErrorActionPreference = "Stop"

$root = "C:\Users\lenovo\Desktop\my-software-main\_gh_upload"
$runtime = Join-Path $root "output\real-data-runtime-20261125"
$storage = Join-Path $root "storage\realdata-20261125"
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
New-Item -ItemType Directory -Path $storage -Force | Out-Null

foreach ($line in Get-Content -LiteralPath (Join-Path $root ".env") -Encoding UTF8) {
    if ($line -match "^([^#=]+)=(.*)$") {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

$env:PYTHONPATH = $root
$env:DATABASE_URL = $env:DATABASE_URL.Replace(":55432/", ":55433/")
$env:OPENSEARCH_URL = "http://127.0.0.1:9201"
$env:OPENSEARCH_INDEX_PREFIX = "realdata_"
$env:STORAGE_ROOT = $storage
$env:CLIP_SERVICE_URL = "http://127.0.0.1:8001"
$env:CLIP_MODEL_PATH = Join-Path $root "models\clip\clip_cn_vit-b-16.pt"
$env:OCR_DET_MODEL_DIR = Join-Path $root "models\ocr\PP-OCRv5_mobile_det"
$env:OCR_REC_MODEL_DIR = Join-Path $root "models\ocr\PP-OCRv5_mobile_rec"
$env:SEARCH_CHANNEL_IMAGE_ENABLED = "true"

$main = Join-Path $root ".venv-main\Scripts\python.exe"
$ocr = Join-Path $root "env_check\.venv-ocr\Scripts\python.exe"
$backend = Join-Path $root "backend"
$ocrDir = Join-Path $root "services\ocr_worker"

$backendProcess = Start-Process `
    -FilePath $main `
    -ArgumentList @("-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtime "backend.out.log") `
    -RedirectStandardError (Join-Path $runtime "backend.err.log") `
    -PassThru

$workerProcess = Start-Process `
    -FilePath $main `
    -ArgumentList @("-m", "app.worker") `
    -WorkingDirectory $backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtime "worker.out.log") `
    -RedirectStandardError (Join-Path $runtime "worker.err.log") `
    -PassThru

$ocrProcess = Start-Process `
    -FilePath $ocr `
    -ArgumentList @("-m", "ocr_worker") `
    -WorkingDirectory $ocrDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtime "ocr.out.log") `
    -RedirectStandardError (Join-Path $runtime "ocr.err.log") `
    -PassThru

@{
    backend = $backendProcess.Id
    worker = $workerProcess.Id
    ocr = $ocrProcess.Id
    clip = 28784
    database_port = 55433
    opensearch_port = 9201
    storage = $storage
    index_prefix = "realdata_"
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime "processes.json") -Encoding UTF8

$deadline = (Get-Date).AddSeconds(180)
do {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
        if ($health.status -in @("ok", "degraded")) {
            $health |
                ConvertTo-Json -Depth 8 |
                Tee-Object -FilePath (Join-Path $runtime "health.json")
            Write-Output "APP_READY=true"
            exit 0
        }
    }
    catch {
    }
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)

Write-Output "APP_READY=false"
Get-Content -Tail 80 (Join-Path $runtime "backend.err.log") -ErrorAction SilentlyContinue
Get-Content -Tail 80 (Join-Path $runtime "worker.err.log") -ErrorAction SilentlyContinue
Get-Content -Tail 80 (Join-Path $runtime "ocr.err.log") -ErrorAction SilentlyContinue
exit 1
