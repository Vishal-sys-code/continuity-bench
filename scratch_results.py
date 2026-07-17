import pandas as pd
import numpy as np
import json
import math

# Load all 5 run summaries
print("=" * 60)
print("PER-RUN CPR BREAKDOWN")
print("=" * 60)

for i in range(1, 6):
    with open(f'results/summary_run_{i}.md', 'r') as f:
        print(f"\n--- Run {i} ---")
        print(f.read())

# Load the final run's raw metrics for detailed analysis
print("\n" + "=" * 60)
print("RAW METRICS ANALYSIS (Final Run = Run 5)")
print("=" * 60)

df = pd.read_csv('results/raw_metrics.csv')
print(f"\nTotal rows: {len(df)}")
print(f"Columns: {list(df.columns)}")

# Split by system
base = df[df['system'] == 'baseline']
treat = df[df['system'] == 'treatment']

# Failover events only
base_fo = base[base['failed_over'] == True]
treat_fo = treat[treat['failed_over'] == True]

print(f"\nBaseline failovers: {len(base_fo)}")
print(f"Treatment failovers: {len(treat_fo)}")

# CPR
base_preserved = base_fo['preserved'].sum()
treat_preserved = treat_fo['preserved'].sum()
print(f"\nBaseline preserved: {base_preserved}/{len(base_fo)} = {base_preserved/len(base_fo)*100:.1f}%")
print(f"Treatment preserved: {treat_preserved}/{len(treat_fo)} = {treat_preserved/len(treat_fo)*100:.1f}%")

# Latency stats (failover events only)
print("\n" + "=" * 60)
print("LATENCY DISTRIBUTION (failover events)")
print("=" * 60)

for name, group in [("Baseline", base_fo), ("Treatment", treat_fo)]:
    lat = group['latency_ms']
    queue = group['queue_wait_ms']
    print(f"\n--- {name} ---")
    print(f"Latency: mean={lat.mean():.1f}, median={lat.median():.1f}, P5={lat.quantile(0.05):.1f}, P25={lat.quantile(0.25):.1f}, P75={lat.quantile(0.75):.1f}, P95={lat.quantile(0.95):.1f}, P99={lat.quantile(0.99):.1f}, max={lat.max():.1f}")
    print(f"Queue:   mean={queue.mean():.1f}, median={queue.median():.1f}, P95={queue.quantile(0.95):.1f}")

# CLO computation
print("\n" + "=" * 60)
print("CLO (Treatment - Baseline latency, per conversation)")
print("=" * 60)

# Merge on conversation_id to get paired CLO
base_lat = base_fo[['conversation_id', 'latency_ms']].rename(columns={'latency_ms': 'base_lat'})
treat_lat = treat_fo[['conversation_id', 'latency_ms']].rename(columns={'latency_ms': 'treat_lat'})
merged = pd.merge(base_lat, treat_lat, on='conversation_id')
merged['clo'] = merged['treat_lat'] - merged['base_lat']
print(f"Paired observations: {len(merged)}")
print(f"CLO: mean={merged['clo'].mean():.1f}, median={merged['clo'].median():.1f}, P5={merged['clo'].quantile(0.05):.1f}, P25={merged['clo'].quantile(0.25):.1f}, P75={merged['clo'].quantile(0.75):.1f}, P95={merged['clo'].quantile(0.95):.1f}")

# Breakdown by turn_count (conversation length)
print("\n" + "=" * 60)
print("BREAKDOWN BY CONVERSATION LENGTH (turn_count)")
print("=" * 60)

for name, group in [("Baseline", base_fo), ("Treatment", treat_fo)]:
    print(f"\n--- {name} ---")
    by_turns = group.groupby('turn_count').agg(
        n=('preserved', 'count'),
        preserved=('preserved', 'sum'),
        mean_lat=('latency_ms', 'mean'),
        median_lat=('latency_ms', 'median'),
        p95_lat=('latency_ms', lambda x: x.quantile(0.95)),
    )
    by_turns['cpr'] = (by_turns['preserved'] / by_turns['n'] * 100).round(1)
    print(by_turns.to_string())
