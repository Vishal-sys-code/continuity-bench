import pandas as pd
import json

df = pd.read_csv('results/raw_metrics.csv')
treatment = df[df['system'] == 'treatment']
treatment_failed_over = treatment[treatment['failed_over'] == True]

top_latency = treatment_failed_over.sort_values(by='latency_ms', ascending=False).head(20)

print(top_latency[['conversation_id', 'turn_count', 'provider', 'latency_ms', 'queue_wait_ms']])

# Calculate correlation between turn_count and latency_ms
corr = treatment_failed_over['turn_count'].corr(treatment_failed_over['latency_ms'])
print(f"\nCorrelation between turn_count and latency_ms: {corr:.2f}")

# Average latency by turn_count
print("\nAverage latency by turn_count:")
print(treatment_failed_over.groupby('turn_count')['latency_ms'].mean().sort_index())
