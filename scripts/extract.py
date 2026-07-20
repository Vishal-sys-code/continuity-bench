import json
with open('bench_logging/baseline_log.jsonl', 'r') as f:
    lines = f.readlines()
count = 0
for line in lines:
    data = json.loads(line)
    if data.get('failed_over') == True:
        print(f"Response: {data['response_text']}")
        print(f"Error: {data['error']}")
        print("-" * 40)
        count += 1
        if count >= 3: break
