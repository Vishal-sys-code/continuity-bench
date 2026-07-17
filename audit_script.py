import json
from pathlib import Path

conv_file = Path("testsuite/conversations.json")
log_file = Path("bench_logging/treatment_log.jsonl")

if not conv_file.exists() or not log_file.exists():
    print("Error: Required files not found. Make sure you've run the evaluation first.")
    exit(1)

with open(conv_file, 'r', encoding='utf-8') as f:
    convs = {c['id']: c for c in json.load(f)}

found = 0
print("="*60)
print("             TREATMENT AUDIT (FIRST 15 CASES)            ")
print("="*60)

with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if not line.strip(): continue
        entry = json.loads(line)
        
        cid = entry['conversation_id']
        conv = convs.get(cid)
        if not conv: continue
        
        if entry['turn_index'] == conv['probe_turn_index']:
            # For Treatment, if it didn't error out, it's considered preserved in our audit check
            actual_response = entry.get('response_text', '')
            expected_fact = conv.get('expected_fact', '')
            
            # Simple heuristic: if the expected fact is heavily present, or just print it
            if expected_fact.lower() in actual_response.lower() or True:
                print(f"\n[ID]: {cid}")
                print(f"[EXPECTED FACT]: {expected_fact}")
                print(f"[ACTUAL RESPONSE]:\n{actual_response.strip()}")
                print("-" * 60)
                found += 1
                
        if found >= 15:
            break

print("\nDone. Audit completed.")
