Stop-Process -Name python -Force -ErrorAction SilentlyContinue

$projectRoot = $PSScriptRoot
$logDir = Join-Path $projectRoot "bench_logging"
$baselineLog = Join-Path $logDir "baseline_log.jsonl"
$treatmentLog = Join-Path $logDir "treatment_log.jsonl"

if (Test-Path $baselineLog) { Remove-Item $baselineLog }
if (Test-Path $treatmentLog) { Remove-Item $treatmentLog }

New-Item -Path $baselineLog -ItemType File | Out-Null
New-Item -Path $treatmentLog -ItemType File | Out-Null

Write-Host "Generating Experiment Manifest..."
python -m fault_injector.generate_manifest --sweep-mode late

Write-Host "Starting Proxies..."
$baselineProcess = Start-Process python -ArgumentList "-u -m systems.baseline.proxy --port 8001 --manifest config/experiment_manifest.json" -WindowStyle Hidden -PassThru -RedirectStandardError baseline.err -RedirectStandardOutput baseline.out
$treatmentProcess = Start-Process python -ArgumentList "-u -m systems.treatment.proxy --port 8002 --manifest config/experiment_manifest.json" -WindowStyle Hidden -PassThru -RedirectStandardError treatment.err -RedirectStandardOutput treatment.out

Start-Sleep -Seconds 8

Write-Host "Running Evaluation..."
python -u -m harness.run_eval --concurrency 15

Write-Host "Cleaning up proxies..."
Stop-Process -Id $baselineProcess.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $treatmentProcess.Id -Force -ErrorAction SilentlyContinue
Write-Host "Done!"
