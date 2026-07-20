#!/usr/bin/env bash
# run_eval.sh - Top-level evaluation entrypoint for Linux/macOS
# 
# Runs the full Phase 2 Continuity Bench evaluation suite.
# This script:
# 1. Checks for required API keys.
# 2. Runs the multi-run evaluation (boots proxies, runs traffic, scores responses).
# 3. Runs the breakdown analysis for negative results.

set -e

# --- 1. Check for API Keys ---
echo -e "\033[0;36mChecking environment variables...\033[0m"
MISSING_KEYS=0

# Load .env if it exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "\033[0;31mX ERROR: OPENAI_API_KEY is not set in environment or .env.\033[0m"
    MISSING_KEYS=1
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "\033[0;31mX ERROR: ANTHROPIC_API_KEY is not set in environment or .env.\033[0m"
    MISSING_KEYS=1
fi

if [ $MISSING_KEYS -eq 1 ]; then
    echo ""
    echo -e "\033[0;33mPlease set the missing API keys before running the evaluation:\033[0m"
    echo "  export OPENAI_API_KEY='sk-...'"
    echo "  export ANTHROPIC_API_KEY='sk-...'"
    exit 1
fi

echo -e "\033[0;32m✓ API keys found.\033[0m"

# --- 2. Run Phase 2 Evaluation ---
echo -e "\n\033[0;36m============================================================\033[0m"
echo -e "\033[0;36mStarting Phase 2 Statistical Analysis (5 Runs, Concurrency 100)\033[0m"
echo -e "\033[0;36m============================================================\033[0m"
# Note: confidence_intervals.py automatically boots and tears down the proxies for each run.
python -m analysis.confidence_intervals --runs 5 --concurrency 100

# --- 3. Run Breakdown Analysis ---
echo -e "\n\033[0;36m============================================================\033[0m"
echo -e "\033[0;36mRunning Subgroup Breakdown & Negative Results Analysis\033[0m"
echo -e "\033[0;36m============================================================\033[0m"
python -m analysis.breakdown

echo -e "\n\033[0;32m============================================================\033[0m"
echo -e "\033[0;32mEvaluation Complete! 🎉\033[0m"
echo "Check the final reports in the 'results/' directory:"
echo " - results/phase2_summary.md"
echo " - results/breakdown.md"
echo -e "\033[0;32m============================================================\033[0m"
