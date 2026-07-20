import json
import random

entries = []
with open('bench_logging/treatment_log.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            entries.append(json.loads(line))

failovers = [e for e in entries if e.get('failed_over')]
random.seed(42)
sample = random.sample(failovers, min(10, len(failovers)))

for i, e in enumerate(sample):
    print(f"--- Conversation {i+1}: {e.get('conversation_id')} Turn {e.get('turn_index')} ---")
    print(f"Latency: {e.get('latency_ms')}ms")
    # To get the prompt, we would need to read from experiment_manifest.json or raw_metrics
    # Let's just print the response fully
    print(f"Response:\n{e.get('response_text')}\n")
