import json
import random
import math

# Load conversations to get probes
with open('testsuite/conversations.json', 'r', encoding='utf-8') as f:
    conversations = json.load(f)

conv_dict = {c['id']: c for c in conversations}

# Load treatment logs
entries = []
with open('bench_logging/treatment_log.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            entries.append(json.loads(line))

failovers = [e for e in entries if e.get('failed_over')]

random.seed(42)
sample = random.sample(failovers, min(10, len(failovers)))

print(f"=== MANUAL AUDIT (10 random treatment failovers from RUN 5) ===\n")
for i, e in enumerate(sample):
    cid = e.get('conversation_id')
    turn = e.get('turn_index', 0)
    conv_data = conv_dict.get(cid)
    
    if not conv_data:
        continue
        
    # Find the setup and probe
    # Turn index in logger is 0-based. But the payload is a list of messages.
    turns = conv_data.get('turns', [])
    setup_msg = turns[0]['content'] if len(turns) > 0 else ""
    user_msgs = [m for m in turns if m['role'] == 'user']
    probe_msg = user_msgs[-1]['content'] if user_msgs else ""
    
    print(f"--- Case {i+1}: {cid} ---")
    print(f"Provider: {e.get('provider')} (Failed over from: {e.get('failover_from')})")
    print(f"Context setup: {setup_msg[:120]}...")
    print(f"PROBE (Last User Msg): {probe_msg}")
    print(f"RESPONSE:\n{e.get('response_text')}")
    print(f"-------------------------\n")

# Compute Wilson Score Interval for N=750, Success=744
n = 750
p = 744 / 750
z = 1.96 # 95% confidence
denominator = 1 + z**2/n
centre_adjusted_probability = p + z**2 / (2*n)
adjusted_standard_deviation = math.sqrt((p*(1 - p) + z**2 / (4*n)) / n)
lower_bound = (centre_adjusted_probability - z*adjusted_standard_deviation) / denominator
upper_bound = (centre_adjusted_probability + z*adjusted_standard_deviation) / denominator

print(f"=== FINAL AGGREGATE CPR ===")
print(f"Total Failovers Evaluated: {n}")
print(f"Successful Preservations: {744}")
print(f"Aggregate CPR: {p*100:.2f}%")
print(f"95% CI (Wilson Score): [{lower_bound*100:.2f}%, {upper_bound*100:.2f}%]")
