#!/usr/bin/env python3
"""
analysis/confidence_intervals.py — Phase 2 Statistical Analysis Pipeline
========================================================================

Runs the full evaluation N times to measure system variance under load.
Computes Continuity Preservation Rate (CPR) using Wilson score intervals
and Continuity Latency Overhead (CLO) using Bootstrap confidence intervals.
"""

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RESULTS_DIR = _PROJECT_ROOT / "results"
_CONFIG_DIR = _PROJECT_ROOT / "config"

def compute_wilson_score(count: int, nobs: int, confidence: float = 0.95) -> tuple[float, float, float]:
    """Compute Wilson score interval for a binomial proportion."""
    if nobs == 0:
        return 0.0, 0.0, 0.0
    
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p = count / nobs
    
    denominator = 1 + z**2 / nobs
    center_adjusted_prob = p + z**2 / (2 * nobs)
    adjusted_std_dev = z * math.sqrt((p * (1 - p) + z**2 / (4 * nobs)) / nobs)
    
    lower_bound = (center_adjusted_prob - adjusted_std_dev) / denominator
    upper_bound = (center_adjusted_prob + adjusted_std_dev) / denominator
    return p, lower_bound, upper_bound

def run_evaluation(run_index: int, concurrency: int, limit: int = None) -> Path:
    """Orchestrate a single evaluation run."""
    print(f"\n{'='*50}\nStarting Run {run_index+1}\n{'='*50}")
    
    # 1. Generate fresh manifest
    print("Generating experiment manifest...")
    subprocess.run([sys.executable, "-m", "fault_injector.generate_manifest", "--sweep-mode", "late"], check=True, cwd=_PROJECT_ROOT)
    
    # 2. Boot Proxies
    print("Booting proxies...")
    manifest_path = _CONFIG_DIR / "experiment_manifest.json"
    
    # Ensure ports are free before booting
    import psutil
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port in (8001, 8002) and conn.pid:
                print(f"Killing process {conn.pid} on port {conn.laddr.port}")
                try:
                    psutil.Process(conn.pid).kill()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass
    except Exception as e:
        print(f"Port cleanup warning: {e}")
            
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
        
    base_env = os.environ.copy()
    base_env["PYTHONUNBUFFERED"] = "1"
    
    base_log_file = open(_RESULTS_DIR / "base_proxy.log", "w")
    treat_log_file = open(_RESULTS_DIR / "treat_proxy.log", "w")
    
    base_proxy = subprocess.Popen(
        [sys.executable, "-m", "systems.baseline.proxy", "--port", "8001", "--manifest", str(manifest_path)],
        cwd=_PROJECT_ROOT, env=base_env, stdout=base_log_file, stderr=base_log_file
    )
    treat_proxy = subprocess.Popen(
        [sys.executable, "-m", "systems.treatment.proxy", "--port", "8002", "--manifest", str(manifest_path)],
        cwd=_PROJECT_ROOT, env=base_env, stdout=treat_log_file, stderr=treat_log_file
    )
    
    time.sleep(5) # Wait for startup
    
    try:
        # 3. Run traffic and LLM judge
        cmd = [sys.executable, "-m", "harness.run_eval", "--concurrency", str(concurrency)]
        if limit is not None:
            cmd.extend(["--limit", str(limit)])
            
        print(f"Running harness (Concurrency: {concurrency})...")
        subprocess.run(cmd, check=True, cwd=_PROJECT_ROOT)
    finally:
        # 4. Teardown
        print("Shutting down proxies...")
        base_proxy.terminate()
        treat_proxy.terminate()
        base_proxy.wait()
        treat_proxy.wait()
        base_log_file.close()
        treat_log_file.close()
        
    # 5. Archive results
    raw_csv = _RESULTS_DIR / "raw_metrics.csv"
    run_csv = _RESULTS_DIR / f"raw_metrics_run_{run_index+1}.csv"
    shutil.copy(raw_csv, run_csv)
    print(f"Saved run data to {run_csv.name}")
    return run_csv

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5, help="Number of independent evaluation runs.")
    parser.add_argument("--concurrency", type=int, default=100, help="Concurrency level for requests.")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit on conversations.")
    args = parser.parse_args()
    
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    run_files = []
    for i in range(args.runs):
        csv_file = run_evaluation(i, args.concurrency, args.limit)
        run_files.append(csv_file)
        
    # --- Statistical Analysis ---
    print("\nComputing statistics across all runs...")
    
    dfs = []
    for i, file in enumerate(run_files):
        df = pd.read_csv(file)
        df["run_id"] = i + 1
        dfs.append(df)
        
    pooled_df = pd.concat(dfs, ignore_index=True)
    
    # Filter only to failovers (since CPR is conditional on failure)
    failovers = pooled_df[pooled_df["failed_over"] == True]
    
    base_failovers = failovers[failovers["system"] == "baseline"]
    treat_failovers = failovers[failovers["system"] == "treatment"]
    
    # CPR per run (for variance)
    run_stats = []
    for i in range(1, args.runs + 1):
        run_base = base_failovers[base_failovers["run_id"] == i]
        run_treat = treat_failovers[treat_failovers["run_id"] == i]
        
        base_cpr = run_base["preserved"].mean() if len(run_base) > 0 else 0
        treat_cpr = run_treat["preserved"].mean() if len(run_treat) > 0 else 0
        
        paired_clo = []
        for cid in run_base["conversation_id"]:
            b_lat = run_base[run_base["conversation_id"] == cid]["latency_ms"].iloc[0]
            t_row = run_treat[run_treat["conversation_id"] == cid]
            if len(t_row) > 0:
                t_lat = t_row["latency_ms"].iloc[0]
                paired_clo.append(t_lat - b_lat)
                
        mean_clo = np.mean(paired_clo) if paired_clo else 0
        run_stats.append({
            "run_id": i,
            "base_cpr": base_cpr,
            "treat_cpr": treat_cpr,
            "mean_clo": mean_clo
        })
        
    # CPR Pooled Wilson Score
    base_n = len(base_failovers)
    base_k = base_failovers["preserved"].sum()
    treat_n = len(treat_failovers)
    treat_k = treat_failovers["preserved"].sum()
    
    b_p, b_lower, b_upper = compute_wilson_score(base_k, base_n)
    t_p, t_lower, t_upper = compute_wilson_score(treat_k, treat_n)
    
    # CLO Paired Differences Bootstrapping
    # Because manifest creates perfect pairs per run, we pair by (run_id, conversation_id)
    paired_df = pd.merge(
        base_failovers[["run_id", "conversation_id", "latency_ms"]],
        treat_failovers[["run_id", "conversation_id", "latency_ms"]],
        on=["run_id", "conversation_id"],
        suffixes=("_base", "_treat")
    )
    
    clo_array = (paired_df["latency_ms_treat"] - paired_df["latency_ms_base"]).to_numpy()
    
    if len(clo_array) > 0:
        clo_mean = np.mean(clo_array)
        clo_median = np.median(clo_array)
        clo_p95 = np.percentile(clo_array, 95)
        
        # Bootstrap Mean
        res_mean = stats.bootstrap((clo_array,), np.mean, n_resamples=1000, confidence_level=0.95, method='percentile')
        mean_ci = (res_mean.confidence_interval.low, res_mean.confidence_interval.high)
        
        # Bootstrap Median
        res_median = stats.bootstrap((clo_array,), np.median, n_resamples=1000, confidence_level=0.95, method='percentile')
        median_ci = (res_median.confidence_interval.low, res_median.confidence_interval.high)
        
        # Bootstrap P95
        def p95_stat(data, axis=None): return np.percentile(data, 95, axis=axis)
        res_p95 = stats.bootstrap((clo_array,), p95_stat, n_resamples=1000, confidence_level=0.95, method='percentile')
        p95_ci = (res_p95.confidence_interval.low, res_p95.confidence_interval.high)
    else:
        clo_mean, clo_median, clo_p95 = 0, 0, 0
        mean_ci, median_ci, p95_ci = (0,0), (0,0), (0,0)
        
    # Generate Markdown
    md = f"""# Continuity Bench: Phase 2 Statistical Analysis
*Runs: {args.runs} | Concurrency: {args.concurrency} | Total Conversations: {len(pooled_df)//2}*

## 1. Continuity Preservation Rate (CPR)
*Wilson Score Intervals (95% CI) computed on pooled failover occurrences.*

| System | Total Failovers | Preserved | CPR (%) | 95% CI (Wilson) |
|---|---|---|---|---|
| **Baseline** | {base_n} | {base_k} | {b_p*100:.1f}% | [{b_lower*100:.1f}%, {b_upper*100:.1f}%] |
| **Treatment** | {treat_n} | {treat_k} | {t_p*100:.1f}% | [{t_lower*100:.1f}%, {t_upper*100:.1f}%] |

## 2. Continuity Latency Overhead (CLO)
*Paired differences (Treatment - Baseline). 95% CIs computed via bootstrap (1000 resamples).*

| Metric | Point Estimate (ms) | 95% CI (Bootstrap) |
|---|---|---|
| **Mean CLO** | {clo_mean:+.1f} | [{mean_ci[0]:+.1f}, {mean_ci[1]:+.1f}] |
| **Median CLO** | {clo_median:+.1f} | [{median_ci[0]:+.1f}, {median_ci[1]:+.1f}] |
| **P95 CLO** | {clo_p95:+.1f} | [{p95_ci[0]:+.1f}, {p95_ci[1]:+.1f}] |

## 3. Run-to-Run Variance
*Independent metrics across the {args.runs} separate runs to assess system jitter under load.*

| Run ID | Baseline CPR (%) | Treatment CPR (%) | Mean CLO (ms) |
|---|---|---|---|
"""
    for stat in run_stats:
        md += f"| Run {stat['run_id']} | {stat['base_cpr']*100:.1f}% | {stat['treat_cpr']*100:.1f}% | {stat['mean_clo']:+.1f} |\n"
        
    md += f"\n**Treatment CPR StdDev:** {np.std([s['treat_cpr'] for s in run_stats])*100:.1f}%\n"
    md += f"**Mean CLO StdDev:** {np.std([s['mean_clo'] for s in run_stats]):.1f}ms\n"

    out_file = _RESULTS_DIR / "phase2_summary.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md)
        
    print(f"\n✓ Completed successfully. Analysis saved to {out_file}")

if __name__ == "__main__":
    main()
