import json
import csv

conv_map = {c["id"]: c for c in json.load(open("testsuite/conversations.json"))}
manifest_map = {m["conversation_id"]: m["failure_turn"] for m in json.load(open("config/experiment_manifest.json"))}

lines = open('bench_logging/treatment_log.jsonl').readlines()
raw_entries = {}
for line in lines:
    if not line.strip(): continue
    entry = json.loads(line)
    cid = entry["conversation_id"]
    tidx = entry["turn_index"]
    if cid in conv_map and cid in manifest_map and tidx == manifest_map[cid]:
        raw_entries[cid] = entry

final_logs = list(raw_entries.values())
found_cids = {entry["conversation_id"] for entry in final_logs}

missing = [cid for cid in conv_map if cid not in found_cids]
print(f"Total in found_cids: {len(found_cids)}")
print(f"Total missing: {len(missing)}")

if 'conv-005' in missing:
    print("conv-005 IS MISSING!")
else:
    print("conv-005 IS IN FOUND_CIDS!")
    print(raw_entries['conv-005']['response_text'])

# And let's check what raw_metrics.csv has
with open('results/raw_metrics.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['conversation_id'] == 'conv-005' and row['system'] == 'treatment':
            print(f"raw_metrics.csv response_text: {row.get('actual_response')}")

