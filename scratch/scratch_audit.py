import json
import random

entries = []
with open('bench_logging/treatment_log.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            entries.append(json.loads(line))

failovers = [e for e in entries if e.get('failed_over')]
print(f"Total failovers found: {len(failovers)}")

random.seed(42)
sample = random.sample(failovers, min(15, len(failovers)))

for i, e in enumerate(sample):
    print(f"--- Conversation {i+1}: {e.get('conversation_id')} Turn {e.get('turn_index')} ---")
    print(f"Provider: {e.get('provider')} (Failed over from: {e.get('failover_from')})")
    print(f"Latency: {e.get('latency_ms')}ms")
    print(f"Response: {e.get('response_text', '')}")
    print()
