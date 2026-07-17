#!/usr/bin/env python3
"""
analysis/breakdown.py — Subgroup Breakdown and Negative Result Flagging
========================================================================

Computes CPR and CLO broken down by:
- Conversation length bucket
- Fallback provider used
- Concurrency level

Flags any subgroup where:
- Treatment CPR < 70%
- Treatment Latency > 2 * Baseline Latency
"""

import glob
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RESULTS_DIR = _PROJECT_ROOT / "results"

def categorize_length(turn_count: int) -> str:
    if turn_count <= 5:
        return "1-5 turns"
    elif turn_count <= 10:
        return "6-10 turns"
    else:
        return "11+ turns"

def main():
    run_files = glob.glob(str(_RESULTS_DIR / "raw_metrics_run_*.csv"))
    if not run_files:
        # Fallback to single run if no multi-run data
        base_file = _RESULTS_DIR / "raw_metrics.csv"
        if base_file.exists():
            run_files = [str(base_file)]
        else:
            print("No raw metrics found in results/. Run evaluation first.")
            sys.exit(1)
            
    print(f"Loading data from {len(run_files)} run files...")
    
    dfs = []
    for i, file in enumerate(run_files):
        try:
            df = pd.read_csv(file)
            if df.empty:
                continue
            df["run_id"] = i + 1
            dfs.append(df)
        except pd.errors.EmptyDataError:
            continue
            
    if not dfs:
        print("No data available.")
        sys.exit(1)
        
    pooled_df = pd.concat(dfs, ignore_index=True)
    
    # Check if required columns are present
    required = {"conversation_id", "system", "failed_over", "latency_ms", "preserved", "provider", "turn_count", "concurrency"}
    missing = required - set(pooled_df.columns)
    if missing:
        print(f"Missing required columns in CSV data: {missing}")
        print("Ensure harness/run_eval.py was updated and run.")
        sys.exit(1)
        
    # Filter to failovers
    failovers = pooled_df[pooled_df["failed_over"] == True].copy()
    
    if failovers.empty:
        print("No failovers recorded in the data.")
        sys.exit(0)
        
    # Add buckets
    failovers["length_bucket"] = failovers["turn_count"].apply(categorize_length)
    
    base = failovers[failovers["system"] == "baseline"]
    treat = failovers[failovers["system"] == "treatment"]
    
    # Merge for paired CLO computation
    merged = pd.merge(
        base, treat,
        on=["run_id", "conversation_id", "provider", "length_bucket", "concurrency"],
        suffixes=("_base", "_treat")
    )
    
    # Grouping variables
    dimensions = ["length_bucket", "provider", "concurrency"]
    
    grouped = merged.groupby(dimensions)
    
    results = []
    flags = []
    
    for name, group in grouped:
        if len(dimensions) == 1:
            name = (name,)
        
        n_conversations = len(group)
        if n_conversations == 0:
            continue
            
        treat_cpr = group["preserved_treat"].mean()
        base_mean_lat = group["latency_ms_base"].mean()
        treat_mean_lat = group["latency_ms_treat"].mean()
        mean_clo = treat_mean_lat - base_mean_lat
        
        row = {
            "Length Bucket": name[0],
            "Provider": name[1],
            "Concurrency": name[2],
            "N": n_conversations,
            "Treatment CPR (%)": treat_cpr * 100,
            "Baseline Lat (ms)": base_mean_lat,
            "Treatment Lat (ms)": treat_mean_lat,
            "CLO (ms)": mean_clo
        }
        results.append(row)
        
        # Check negative results thresholds
        issues = []
        if treat_cpr < 0.70:
            issues.append(f"Low CPR ({treat_cpr*100:.1f}%)")
        if treat_mean_lat > 2.0 * base_mean_lat:
            issues.append(f"High CLO (Treatment > 2x Baseline)")
            
        if issues:
            flags.append({
                "Group": f"{name[0]} | {name[1]} | Concurrency {name[2]}",
                "Issues": ", ".join(issues),
                "CPR": f"{treat_cpr*100:.1f}%",
                "Latencies": f"Base: {base_mean_lat:.1f}ms, Treat: {treat_mean_lat:.1f}ms (CLO: {mean_clo:+.1f}ms)"
            })
            
    res_df = pd.DataFrame(results)
    
    # Generate Markdown
    md = f"# Subgroup Breakdown and Negative Results\n"
    md += "*Aggregated across all runs to highlight performance degradation in specific edge cases.*\n\n"
    
    md += "## Detailed Subgroup Metrics\n\n"
    
    # Format table manually for better control
    headers = ["Length Bucket", "Provider", "Concurrency", "N", "Treatment CPR (%)", "Baseline Lat (ms)", "Treatment Lat (ms)", "CLO (ms)"]
    md += "|" + "|".join(headers) + "|\n"
    md += "|" + "|".join(["---"] * len(headers)) + "|\n"
    
    for _, r in res_df.iterrows():
        md += f"|{r['Length Bucket']}|{r['Provider']}|{r['Concurrency']}|{r['N']}|{r['Treatment CPR (%)']:.1f}%|{r['Baseline Lat (ms)']:.1f}|{r['Treatment Lat (ms)']:.1f}|{r['CLO (ms)']:+.1f}|\n"
        
    md += "\n## ⚠️ Candidate Negative Results\n"
    md += "*Subgroups explicitly flagged where Treatment CPR < 70% or Treatment Latency > 2x Baseline.*\n\n"
    
    if not flags:
        md += "✅ **No negative results detected.** All subgroups maintained >=70% CPR and <2x latency overhead.\n"
    else:
        for f in flags:
            md += f"### {f['Group']}\n"
            md += f"- **Issues Identified**: {f['Issues']}\n"
            md += f"- **CPR**: {f['CPR']}\n"
            md += f"- **Latencies**: {f['Latencies']}\n\n"
            
    out_file = _RESULTS_DIR / "breakdown.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md)
        
    print(f"\n✓ Breakdown analysis complete. Output saved to {out_file}")
    
    if flags:
        print(f"⚠️  Found {len(flags)} candidate negative results! Check the markdown report.")

if __name__ == "__main__":
    main()
