#!/usr/bin/env python3
"""
harness/run_eval.py — End-to-end evaluation orchestrator
=========================================================

Orchestrates the full continuity-bench evaluation pipeline:
1. Validates proxies are running.
2. Runs all 150 conversations against both baseline and treatment proxies.
3. Scores the final probe responses using the LLM judge.
4. Computes CPR (Continuity Preservation Rate) and CLO (Continuity Latency Overhead).
5. Outputs results to results/summary.md and results/raw_metrics.csv.

Ensure that the baseline and treatment proxies are already running, 
preferably with `--sweep-mode late` so failures are injected at the probe turn:
  Baseline : http://localhost:8001
  Treatment: http://localhost:8002

Usage:
    python -m harness.run_eval
"""

import asyncio
import csv
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean

import httpx
import numpy as np

# Import our existing judge and runner modules natively
from harness.runner import play_conversation
from harness.judge import score_response
import openai

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Configuration ---
BASELINE_URL = "http://localhost:8001"
TREATMENT_URL = "http://localhost:8002"
CONVERSATIONS_FILE = _PROJECT_ROOT / "testsuite" / "conversations.json"
RESULTS_DIR = _PROJECT_ROOT / "results"
SUMMARY_OUT = RESULTS_DIR / "summary.md"
CSV_OUT = RESULTS_DIR / "raw_metrics.csv"
CONCURRENCY = 5

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

async def check_proxies():
    print("Checking proxy health...")
    async with httpx.AsyncClient() as client:
        try:
            r1 = await client.get(f"{BASELINE_URL}/health", timeout=300.0)
            r1.raise_for_status()
            r2 = await client.get(f"{TREATMENT_URL}/health", timeout=300.0)
            r2.raise_for_status()
            print("✓ Both proxies are online.")
        except httpx.HTTPError as e:
            print(f"Error: Could not reach proxies. Ensure they are running on 8001 and 8002. ({e})")
            sys.exit(1)

async def run_traffic(conversations: list[dict], proxy_url: str) -> dict[str, float]:
    sem = asyncio.Semaphore(CONCURRENCY)
    harness_latencies = {}
    async with httpx.AsyncClient(timeout=600.0) as client:
        async def bounded_play(conv):
            async with sem:
                cid, lat = await play_conversation(client, proxy_url, conv)
                harness_latencies[cid] = lat
        
        tasks = [asyncio.create_task(bounded_play(conv)) for conv in conversations]
        await asyncio.gather(*tasks)
    return harness_latencies

async def parse_logs_and_judge(conversations: list[dict], log_file: Path, system: str, manifest_map: dict[str, int], harness_latencies: dict[str, float]):
    conv_map = {c["id"]: c for c in conversations}
    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    sem = asyncio.Semaphore(10)
    
    judgments = []
    
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    raw_entries = {}
    for line in lines:
        if not line.strip(): continue
        entry = json.loads(line)
        cid = entry["conversation_id"]
        tidx = entry["turn_index"]
        if cid in conv_map and cid in manifest_map and tidx == manifest_map[cid]:
            raw_entries[cid] = entry # Overwrites earlier attempts, keeping only the final retry
            
    final_logs = list(raw_entries.values())
            
    found_cids = {entry["conversation_id"] for entry in final_logs}
    for cid in conv_map:
        if cid not in found_cids:
            final_logs.append({
                "conversation_id": cid,
                "turn_index": manifest_map.get(cid, conv_map[cid]["probe_turn_index"]),
                "failed_over": True,
                "latency_ms": 0.0,
                "response_text": "",
                "error": "[PIPELINE ABORTED] Connection dropped or proxy timed out."
            })
            
    print(f"[{system}] Judging {len(final_logs)} probe responses...")
    
    async def process(entry):
        cid = entry["conversation_id"]
        conv = conv_map[cid]
        expected = conv["expected_fact"]
        target_turn = manifest_map.get(cid, conv["probe_turn_index"])
        probe_question = conv["turns"][target_turn]["content"]
        actual_response = entry["response_text"]
        
        async with sem:
            preserved, reasoning = await score_response(client, expected, probe_question, actual_response)
            
        harness_lat = harness_latencies.get(cid, 0.0)
        proxy_lat = entry.get("latency_ms", 0.0)
        queue_wait_ms = max(0.0, harness_lat - proxy_lat)
        
        judgments.append({
            "conversation_id": cid,
            "system": system,
            "failed_over": entry.get("failed_over", False),
            "latency_ms": proxy_lat,
            "queue_wait_ms": queue_wait_ms,
            "expected_fact": expected,
            "actual_response": actual_response,
            "preserved": preserved,
            "reasoning": reasoning,
            "provider": entry.get("provider", "unknown"),
            "turn_count": len(conv["turns"]),
            "concurrency": CONCURRENCY
        })
        
    tasks = [asyncio.create_task(process(entry)) for entry in final_logs]
    await asyncio.gather(*tasks)
    return judgments

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of conversations to run for a faster test")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent requests")
    args = parser.parse_args()
    
    global CONCURRENCY
    CONCURRENCY = args.concurrency
    
    RESULTS_DIR.mkdir(exist_ok=True)
    await check_proxies()
    
    with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
        conversations = json.load(f)
        
    if args.limit:
        conversations = conversations[:args.limit]
        print(f"Limiting to {args.limit} conversations for a quick run.")
        
    manifest_path = _PROJECT_ROOT / "config" / "experiment_manifest.json"
    if not manifest_path.exists():
        print(f"Error: {manifest_path} not found. Run generate_manifest.py first.", file=sys.stderr)
        sys.exit(1)
        
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    manifest_map = {m["conversation_id"]: m["failure_turn"] for m in manifest_data}
        
    # We rely on the proxy's internal logging for latency tracking.
    # To ensure clean data, we clear existing logs.
    baseline_log = _PROJECT_ROOT / "bench_logging" / "baseline_log.jsonl"
    treatment_log = _PROJECT_ROOT / "bench_logging" / "treatment_log.jsonl"
    
    if baseline_log.exists():
        try:
            baseline_log.unlink()
        except PermissionError:
            baseline_log.write_text("", encoding="utf-8")
    if treatment_log.exists():
        try:
            treatment_log.unlink()
        except PermissionError:
            treatment_log.write_text("", encoding="utf-8")
    
    # 1. Run Traffic
    print(f"\n--- Phase 1: Running Traffic (N={len(conversations)} conversations) ---")
    
    print("Running baseline traffic...")
    t0 = time.perf_counter()
    base_latencies = await run_traffic(conversations, BASELINE_URL)
    print(f"✓ Baseline finished in {time.perf_counter()-t0:.1f}s")
    
    print("Running treatment traffic...")
    t0 = time.perf_counter()
    treat_latencies = await run_traffic(conversations, TREATMENT_URL)
    print(f"✓ Treatment finished in {time.perf_counter()-t0:.1f}s")
    
    # 2. Score with LLM
    print("\n--- Phase 2: LLM Judging ---")
    base_judgments = await parse_logs_and_judge(conversations, baseline_log, "baseline", manifest_map, base_latencies)
    treat_judgments = await parse_logs_and_judge(conversations, treatment_log, "treatment", manifest_map, treat_latencies)
    
    all_judgments = base_judgments + treat_judgments
    
    # 3. Save Raw Data (CSV)
    print("\n--- Phase 3: Metrics Computation ---")
    
    with open(CSV_OUT, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["conversation_id", "system", "failed_over", "latency_ms", "queue_wait_ms", "preserved", "expected_fact", "reasoning", "provider", "turn_count", "concurrency"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in all_judgments:
            writer.writerow(row)
    print(f"✓ Saved raw data to {CSV_OUT}")
    
    # 4. Compute Metrics
    # Filter only to turns that experienced a failover and where the judge succeeded
    base_failovers = [j for j in base_judgments if j["failed_over"] and j["preserved"] is not None]
    treat_failovers = [j for j in treat_judgments if j["failed_over"] and j["preserved"] is not None]
    
    # CPR
    base_cpr_succ = sum(1 for j in base_failovers if j["preserved"])
    base_cpr_n = len(base_failovers)
    base_cpr = (base_cpr_succ / base_cpr_n) if base_cpr_n > 0 else 0
    base_cpr_ci = wilson_score_interval(base_cpr_succ, base_cpr_n)
    
    treat_cpr_succ = sum(1 for j in treat_failovers if j["preserved"])
    treat_cpr_n = len(treat_failovers)
    treat_cpr = (treat_cpr_succ / treat_cpr_n) if treat_cpr_n > 0 else 0
    treat_cpr_ci = wilson_score_interval(treat_cpr_succ, treat_cpr_n)
    
    # CLO (Latency)
    base_lats = [j["latency_ms"] for j in base_failovers]
    treat_lats = [j["latency_ms"] for j in treat_failovers]
    
    base_qs = [j["queue_wait_ms"] for j in base_failovers]
    treat_qs = [j["queue_wait_ms"] for j in treat_failovers]
    
    base_mean_lat = mean(base_lats) if base_lats else 0
    treat_mean_lat = mean(treat_lats) if treat_lats else 0
    
    base_mean_q = mean(base_qs) if base_qs else 0
    treat_mean_q = mean(treat_qs) if treat_qs else 0
    
    base_p95_lat = np.percentile(base_lats, 95) if base_lats else 0
    treat_p95_lat = np.percentile(treat_lats, 95) if treat_lats else 0
    
    base_p95_q = np.percentile(base_qs, 95) if base_qs else 0
    treat_p95_q = np.percentile(treat_qs, 95) if treat_qs else 0
    
    clo_mean = treat_mean_lat - base_mean_lat
    clo_p95 = treat_p95_lat - base_p95_lat
    
    # 5. Output Summary Markdown
    md_content = f"""# Continuity Bench Evaluation Results

## 1. Continuity Preservation Rate (CPR)
*Evaluated exclusively on failover occurrences (N={base_cpr_n} baseline, N={treat_cpr_n} treatment).*

| System | CPR (%) | 95% CI |
|---|---|---|
| **Baseline (Stateless)** | {base_cpr*100:.1f}% | [{base_cpr_ci[0]*100:.1f}%, {base_cpr_ci[1]*100:.1f}%] |
| **Treatment (History-Forwarding)** | {treat_cpr*100:.1f}% | [{treat_cpr_ci[0]*100:.1f}%, {treat_cpr_ci[1]*100:.1f}%] |

## 2. Continuity Latency Overhead (CLO)
*Additional latency incurred by forwarding the full context history during a failover.*

| Metric | Baseline Latency (ms) | Treatment Latency (ms) | CLO (Overhead ms) | Baseline Queue (ms) | Treatment Queue (ms) |
|---|---|---|---|---|---|
| **Mean** | {base_mean_lat:.1f} | {treat_mean_lat:.1f} | **{clo_mean:+.1f}** | {base_mean_q:.1f} | {treat_mean_q:.1f} |
| **P95** | {base_p95_lat:.1f} | {treat_p95_lat:.1f} | **{clo_p95:+.1f}** | {base_p95_q:.1f} | {treat_p95_q:.1f} |
"""
    
    with open(SUMMARY_OUT, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print(f"✓ Saved summary table to {SUMMARY_OUT}")
    print("\n" + "="*50)
    print(md_content)
    print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
