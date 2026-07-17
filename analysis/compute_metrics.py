#!/usr/bin/env python3
"""
analysis/compute_metrics.py — Compute CPR and CIs from scored logs
===================================================================

Computes the primary evaluation metrics for continuity-bench:
- CPR (Context Preservation Rate): The percentage of conversations
  where the expected fact was successfully preserved/recalled.
- Stratified by whether the conversation experienced a failover or not.
- Calculates 95% Confidence Intervals (CIs) for these rates.

Usage:
    python -m analysis.compute_metrics --baseline results/baseline_scored.jsonl \
                                       --treatment results/treatment_scored.jsonl
"""

import argparse
import json
import math
import sys
from pathlib import Path

def wilson_score_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Calculate the Wilson score interval for a binomial proportion (95% CI by default)."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    denominator = 1 + z**2 / n
    centre_adjusted_prob = p + z**2 / (2 * n)
    adjusted_std_dev = math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    
    lower_bound = (centre_adjusted_prob - z * adjusted_std_dev) / denominator
    upper_bound = (centre_adjusted_prob + z * adjusted_std_dev) / denominator
    
    return max(0.0, lower_bound), min(1.0, upper_bound)

def analyze_scored_file(filepath: str, name: str) -> dict:
    if not Path(filepath).exists():
        return None
        
    total_convs = 0
    total_preserved = 0
    
    failover_convs = 0
    failover_preserved = 0
    
    no_failover_convs = 0
    no_failover_preserved = 0
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            
            preserved = entry["preserved"]
            failed_over = entry["failed_over"]
            
            total_convs += 1
            if preserved: total_preserved += 1
            
            if failed_over:
                failover_convs += 1
                if preserved: failover_preserved += 1
            else:
                no_failover_convs += 1
                if preserved: no_failover_preserved += 1
                
    def make_stats(succ, n):
        if n == 0: return {"rate": 0.0, "n": 0, "ci_lower": 0.0, "ci_upper": 0.0}
        rate = succ / n
        ci_l, ci_u = wilson_score_interval(succ, n)
        return {"rate": rate, "n": n, "ci_lower": ci_l, "ci_upper": ci_u}
        
    return {
        "system": name,
        "overall": make_stats(total_preserved, total_convs),
        "failover": make_stats(failover_preserved, failover_convs),
        "no_failover": make_stats(no_failover_preserved, no_failover_convs)
    }

def print_table(results: list[dict]):
    print(f"\n{'='*70}")
    print(f"{'CONTINUITY-BENCH RESULTS':^70}")
    print(f"{'='*70}\n")
    
    for r in results:
        sys_name = r["system"].upper()
        overall = r["overall"]
        failover = r["failover"]
        no_failover = r["no_failover"]
        
        print(f"System: {sys_name}")
        print("-" * 30)
        
        o_rate = overall['rate']*100
        o_cl = overall['ci_lower']*100
        o_cu = overall['ci_upper']*100
        print(f"Overall CPR:      {o_rate:5.1f}%  (95% CI: {o_cl:4.1f}% - {o_cu:4.1f}%)  [N={overall['n']}]")
        
        nf_rate = no_failover['rate']*100
        nf_cl = no_failover['ci_lower']*100
        nf_cu = no_failover['ci_upper']*100
        print(f"Clean (No Fault): {nf_rate:5.1f}%  (95% CI: {nf_cl:4.1f}% - {nf_cu:4.1f}%)  [N={no_failover['n']}]")
        
        f_rate = failover['rate']*100
        f_cl = failover['ci_lower']*100
        f_cu = failover['ci_upper']*100
        print(f"Failover Turns:   {f_rate:5.1f}%  (95% CI: {f_cl:4.1f}% - {f_cu:4.1f}%)  [N={failover['n']}]")
        print("\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=str, required=True, help="Path to baseline scored JSONL")
    parser.add_argument("--treatment", type=str, required=True, help="Path to treatment scored JSONL")
    args = parser.parse_args()
    
    results = []
    
    b_res = analyze_scored_file(args.baseline, "Baseline (Stateless)")
    if b_res: results.append(b_res)
    else: print(f"Warning: Baseline logs not found at {args.baseline}")
    
    t_res = analyze_scored_file(args.treatment, "Treatment (History-Forwarding)")
    if t_res: results.append(t_res)
    else: print(f"Warning: Treatment logs not found at {args.treatment}")
    
    if not results:
        print("No results found to analyze.")
        sys.exit(1)
        
    print_table(results)
    
    # Save a summary file to results/
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    summary_path = out_dir / "summary_metrics.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved summary metrics to {summary_path}")

if __name__ == "__main__":
    main()
