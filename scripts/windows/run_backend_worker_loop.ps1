param(
    [Parameter(Mandatory = $true)]
    [string]$Python,
    [Parameter(Mandatory = $true)]
    [string]$StopFile
)

$ErrorActionPreference = "Stop"
while (-not (Test-Path -LiteralPath $StopFile)) {
    & $Python -m app.worker
    $code = $LASTEXITCODE
    if ($code -eq 130) {
        exit 0
    }
    if ($code -ne 0) {
        exit $code
    }
    Start-Sleep -Seconds 1
}
