$ErrorActionPreference = "Stop"

$env:Path = "C:\Program Files\Docker\Docker\resources\bin;C:\Program Files\Docker\cli-plugins;" + $env:Path
$root = "C:\Users\lenovo\Desktop\my-software-main\_gh_upload"
$dataset = "C:\Users\lenovo\Desktop\my-software-main\w8-data\docvqa-crash4"
$out = Join-Path $root "output\w8-round2c-20261125"
$storage = Join-Path $root "storage\w8-round2c-20261125"
New-Item -ItemType Directory -Path $out -Force | Out-Null
New-Item -ItemType Directory -Path $storage -Force | Out-Null

$dbExists = ((& docker exec docmgr-postgres-1 psql -U docmgr -d postgres -Atc "select 1 from pg_database where datname='docmgr_w8_round2c_20261125'") -join "").Trim()
if ($dbExists -ne "1") {
    & docker exec docmgr-postgres-1 createdb -U docmgr docmgr_w8_round2c_20261125
}

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

$python = Join-Path $root ".venv-main\Scripts\python.exe"
$backend = Join-Path $root "backend"
Push-Location $backend
try {
    & $python -m alembic upgrade head 2>&1 |
        Tee-Object -FilePath (Join-Path $out "alembic.txt")
    if ($LASTEXITCODE -ne 0) { throw "alembic failed" }

    & $python -m app.modules.experiments --root $dataset validate 2>&1 |
        Tee-Object -FilePath (Join-Path $out "validate.txt")
    if ($LASTEXITCODE -ne 0) { throw "validate failed" }

    & $python -m app.modules.experiments --root $dataset import 2>&1 |
        Tee-Object -FilePath (Join-Path $out "import.txt")
    if ($LASTEXITCODE -ne 0) { throw "import failed" }
}
finally {
    Pop-Location
}

Write-Output "W8_ROUND2_SETUP_READY"
