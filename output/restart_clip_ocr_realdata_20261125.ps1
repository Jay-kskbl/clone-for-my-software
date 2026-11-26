$ErrorActionPreference = "Stop"

$root = "C:\Users\lenovo\Desktop\my-software-main\_gh_upload"
$runtime = Join-Path $root "output\real-data-runtime-20261125"
$ocrDir = Join-Path $root "services\ocr_worker"
$clipDir = Join-Path $root "services\clip_service"

foreach ($line in Get-Content -LiteralPath (Join-Path $root ".env") -Encoding UTF8) {
    if ($line -match "^([^#=]+)=(.*)$") {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

$env:PYTHONPATH = $root
$env:DATABASE_URL = $env:DATABASE_URL.Replace(":55432/", ":55433/")
$env:OPENSEARCH_URL = "http://127.0.0.1:9201"
$env:OPENSEARCH_INDEX_PREFIX = "realdata_"
$env:STORAGE_ROOT = Join-Path $root "storage\realdata-20261125"
$env:CLIP_MODEL_PATH = Join-Path $root "models\clip\clip_cn_vit-b-16.pt"
$env:CLIP_SERVICE_URL = "http://127.0.0.1:8001"
$env:OCR_DET_MODEL_DIR = Join-Path $root "models\ocr\PP-OCRv5_mobile_det"
$env:OCR_REC_MODEL_DIR = Join-Path $root "models\ocr\PP-OCRv5_mobile_rec"

$clipPython = Join-Path $root "env_check\.venv-clip\Scripts\python.exe"
$ocrPython = Join-Path $root "env_check\.venv-ocr\Scripts\python.exe"

$clip = Start-Process `
    -FilePath $clipPython `
    -ArgumentList @("-m", "clip_service") `
    -WorkingDirectory $clipDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtime "clip-restart.out.log") `
    -RedirectStandardError (Join-Path $runtime "clip-restart.err.log") `
    -PassThru

$ocr = Start-Process `
    -FilePath $ocrPython `
    -ArgumentList @("-m", "ocr_worker") `
    -WorkingDirectory $ocrDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtime "ocr-restart.out.log") `
    -RedirectStandardError (Join-Path $runtime "ocr-restart.err.log") `
    -PassThru

@{
    clip = $clip.Id
    ocr = $ocr.Id
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime "aux-restart-processes.json") -Encoding UTF8

$deadline = (Get-Date).AddSeconds(180)
do {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -TimeoutSec 5
        if ($health.status -eq "ok") {
            $health |
                ConvertTo-Json -Depth 8 |
                Tee-Object -FilePath (Join-Path $runtime "clip-health-after-restart.json")
            Write-Output "CLIP_READY=true"
            Write-Output "CLIP_PID=$($clip.Id)"
            Write-Output "OCR_PID=$($ocr.Id)"
            exit 0
        }
    }
    catch {
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

Write-Output "CLIP_READY=false"
Get-Content -Tail 100 (Join-Path $runtime "clip-restart.err.log") -ErrorAction SilentlyContinue
Get-Content -Tail 100 (Join-Path $runtime "ocr-restart.err.log") -ErrorAction SilentlyContinue
exit 1
