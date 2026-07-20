<#
.SYNOPSIS
run_eval.ps1 - Top-level evaluation entrypoint for Windows

.DESCRIPTION
Runs the full Phase 2 Continuity Bench evaluation suite.
This script:
1. Checks for required API keys.
2. Runs the multi-run evaluation (boots proxies, runs traffic, scores responses).
3. Runs the breakdown analysis for negative results.
#>

$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"

# --- 1. Check for API Keys ---
Write-Host "Checking environment variables..." -ForegroundColor Cyan

$HasOpenAI = [bool]$env:OPENAI_API_KEY

if (Test-Path ".env") {
    $EnvContent = Get-Content ".env" -Raw
    if ($EnvContent -match "(?m)^OPENAI_API_KEY\s*=") { $HasOpenAI = $true }
}

if (-not $HasOpenAI) {
    Write-Host "X ERROR: OPENAI_API_KEY is not set in environment or .env." -ForegroundColor Red
    Write-Host ""
    Write-Host "Please set the API key before running the evaluation:" -ForegroundColor Yellow
    Write-Host "  `$env:OPENAI_API_KEY='sk-...'"
    exit 1
}

Write-Host "✓ API keys found." -ForegroundColor Green

# --- 2. Run Phase 2 Evaluation ---
Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "Starting Phase 2 Statistical Analysis (5 Runs, Concurrency 100)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
# Note: confidence_intervals.py automatically boots and tears down the proxies for each run.
python -m analysis.confidence_intervals --runs 5 --concurrency 100

# --- 3. Run Breakdown Analysis ---
Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "Running Subgroup Breakdown & Negative Results Analysis" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
python -m analysis.breakdown

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "Evaluation Complete! 🎉" -ForegroundColor Green
Write-Host "Check the final reports in the 'results/' directory:"
Write-Host " - results/phase2_summary.md"
Write-Host " - results/breakdown.md"
Write-Host "============================================================" -ForegroundColor Green
