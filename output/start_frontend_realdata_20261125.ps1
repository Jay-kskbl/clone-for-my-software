$ErrorActionPreference = "Stop"

$root = "C:\Users\lenovo\Desktop\my-software-main\_gh_upload"
$frontend = Join-Path $root "frontend"
$runtime = Join-Path $root "output\real-data-runtime-20261125"
$node = (Get-Command node).Source
New-Item -ItemType Directory -Path $runtime -Force | Out-Null

$process = Start-Process `
    -FilePath $node `
    -ArgumentList @(
        (Join-Path $frontend "node_modules\vite\bin\vite.js"),
        "--host",
        "127.0.0.1",
        "--port",
        "5173"
    ) `
    -WorkingDirectory $frontend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtime "frontend.out.log") `
    -RedirectStandardError (Join-Path $runtime "frontend.err.log") `
    -PassThru

Write-Output "FRONTEND_PID=$($process.Id)"

$deadline = (Get-Date).AddSeconds(90)
do {
    try {
        $response = Invoke-WebRequest `
            -Uri "http://127.0.0.1:5173" `
            -UseBasicParsing `
            -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            Write-Output "FRONTEND_READY=true"
            exit 0
        }
    }
    catch {
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

Write-Output "FRONTEND_READY=false"
Get-Content -Tail 80 (Join-Path $runtime "frontend.err.log") -ErrorAction SilentlyContinue
exit 1
