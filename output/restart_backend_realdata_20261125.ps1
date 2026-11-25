$ErrorActionPreference = "Stop"

$root = "C:\Users\lenovo\Desktop\my-software-main\_gh_upload"
$runtime = Join-Path $root "output\real-data-runtime-20261125"
$storage = Join-Path $root "storage\realdata-20261125"

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

$python = Join-Path $root ".venv-main\Scripts\python.exe"
$backend = Join-Path $root "backend"
$process = Start-Process `
    -FilePath $python `
    -ArgumentList @(
        "-m",
        "uvicorn",
        "app.main:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8000"
    ) `
    -WorkingDirectory $backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtime "backend-restart.out.log") `
    -RedirectStandardError (Join-Path $runtime "backend-restart.err.log") `
    -PassThru

Write-Output "BACKEND_RESTART_PID=$($process.Id)"
$deadline = (Get-Date).AddSeconds(120)
do {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
        if ($health.status -in @("ok", "degraded")) {
            $health |
                ConvertTo-Json -Depth 8 |
                Tee-Object -FilePath (Join-Path $runtime "health-after-restart.json")
            Write-Output "BACKEND_READY=true"
            exit 0
        }
    }
    catch {
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

Write-Output "BACKEND_READY=false"
Get-Content -Tail 100 (Join-Path $runtime "backend-restart.err.log") -ErrorAction SilentlyContinue
exit 1
