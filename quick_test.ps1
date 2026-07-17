$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Killing any old proxy processes..." -ForegroundColor Yellow
$netstat = netstat -ano | Select-String "8001|8002"
foreach ($line in $netstat) {
    if ($line -match "\s+(\d+)\s*$") {
        $pidToKill = $matches[1]
        try { Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue } catch {}
    }
}
Start-Sleep -Seconds 1

Write-Host "Booting Baseline Proxy on port 8001..." -ForegroundColor Cyan
$baseProc = Start-Process -NoNewWindow -PassThru -FilePath "python.exe" -ArgumentList "-m systems.baseline.proxy --port 8001 --config config/providers.yaml --manifest config/experiment_manifest.json"

Write-Host "Booting Treatment Proxy on port 8002..." -ForegroundColor Cyan
$treatProc = Start-Process -NoNewWindow -PassThru -FilePath "python.exe" -ArgumentList "-m systems.treatment.proxy --port 8002 --config config/providers.yaml --manifest config/experiment_manifest.json"

Write-Host "Waiting for proxies to initialize..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r1 = Invoke-WebRequest -Uri "http://localhost:8001/health" -UseBasicParsing -ErrorAction SilentlyContinue
        $r2 = Invoke-WebRequest -Uri "http://localhost:8002/health" -UseBasicParsing -ErrorAction SilentlyContinue
        if ($r1.StatusCode -eq 200 -and $r2.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {}
}

if (-not $ready) {
    Write-Host "Error: Proxies failed to start in time!" -ForegroundColor Red
    Stop-Process -Id $baseProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $treatProc.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "Proxies are ready! Running evaluation harness..." -ForegroundColor Green
try {
    python.exe -m harness.run_eval --concurrency 100
} finally {
    Write-Host "Cleaning up proxies..." -ForegroundColor Yellow
    Stop-Process -Id $baseProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $treatProc.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Done!" -ForegroundColor Green
