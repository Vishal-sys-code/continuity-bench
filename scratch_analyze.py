import json

entries = []
with open('bench_logging/treatment_log.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            entries.append(json.loads(line))

failovers = [e for e in entries if e.get('failed_over')]
print(f"Total failovers: {len(failovers)}")

long_ones = [e for e in failovers if e.get('latency_ms', 0) > 15000]
print(f"Long failovers (>15s): {len(long_ones)}")

for e in sorted(long_ones, key=lambda x: x['latency_ms'], reverse=True)[:10]:
    print(f"Conv: {e['conversation_id']}, Turn: {e['turn_index']}, Latency: {e['latency_ms']}ms, Error: {e.get('error')}")
