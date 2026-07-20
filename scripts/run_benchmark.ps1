$env:OPENAI_API_KEY="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"
$env:ANTHROPIC_API_KEY="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"

Write-Host "Generating Experiment Manifest..."
python -m fault_injector.generate_manifest --sweep-mode late

Write-Host "Starting baseline proxy on port 8001..."
$baseline = Start-Process python -ArgumentList "-m systems.baseline.proxy --port 8001 --manifest config/experiment_manifest.json" -PassThru -WindowStyle Hidden

Write-Host "Starting treatment proxy on port 8002..."
$treatment = Start-Process python -ArgumentList "-m systems.treatment.proxy --port 8002 --manifest config/experiment_manifest.json" -PassThru -WindowStyle Hidden

Write-Host "Waiting 5 seconds for proxies to boot..."
Start-Sleep -Seconds 5

Write-Host "Running evaluation harness against baseline..."
python -m harness.runner --proxy http://localhost:8001

Write-Host "Running evaluation harness against treatment..."
python -m harness.runner --proxy http://localhost:8002

Write-Host "Scoring baseline responses..."
python -m harness.judge --logs bench_logging/baseline_log.jsonl --output results/baseline_scored.jsonl

Write-Host "Scoring treatment responses..."
python -m harness.judge --logs bench_logging/treatment_log.jsonl --output results/treatment_scored.jsonl

Write-Host "Computing metrics..."
python -m analysis.compute_metrics --baseline results/baseline_scored.jsonl --treatment results/treatment_scored.jsonl

Write-Host "Cleaning up proxies..."
Stop-Process -Id $baseline.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $treatment.Id -Force -ErrorAction SilentlyContinue

Write-Host "Benchmark complete!"
