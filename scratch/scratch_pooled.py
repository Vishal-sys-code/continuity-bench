import json
import math

# Collect per-run CPR data from the summaries we already have
# Run 1: 99.3%, Run 2: 99.3%, Run 3: 99.3%, Run 4: 98.7%, Run 5: 99.3%
# That's 149+149+149+148+149 = 744 out of 750

# Per-run treatment successes
treat_successes = [149, 149, 149, 148, 149]  # from 99.3, 99.3, 99.3, 98.7, 99.3
treat_n = [150] * 5

# Per-run baseline successes
base_successes = [0, 0, 0, 0, 0]  # all 0.0%
base_n = [150] * 5

# Pooled
total_treat_success = sum(treat_successes)
total_treat_n = sum(treat_n)
total_base_success = sum(base_successes)
total_base_n = sum(base_n)

def wilson_ci(successes, n, z=1.96):
    p = successes / n
    denom = 1 + z**2/n
    centre = p + z**2/(2*n)
    adj_std = math.sqrt((p*(1-p) + z**2/(4*n)) / n)
    lo = (centre - z*adj_std) / denom
    hi = (centre + z*adj_std) / denom
    return max(0,lo), min(1,hi)

print("POOLED AGGREGATE RESULTS (N=750)")
print(f"Treatment: {total_treat_success}/{total_treat_n} = {total_treat_success/total_treat_n*100:.2f}%")
lo, hi = wilson_ci(total_treat_success, total_treat_n)
print(f"  Wilson 95% CI: [{lo*100:.2f}%, {hi*100:.2f}%]")

print(f"Baseline:  {total_base_success}/{total_base_n} = {total_base_success/total_base_n*100:.2f}%")
lo, hi = wilson_ci(total_base_success, total_base_n)
print(f"  Wilson 95% CI: [{lo*100:.2f}%, {hi*100:.2f}%]")

# Per-run table
print("\nPER-RUN CPR TABLE")
print(f"{'Run':>4} | {'Baseline':>10} | {'Treatment':>10}")
for i in range(5):
    bp = base_successes[i]/base_n[i]*100
    tp = treat_successes[i]/treat_n[i]*100
    print(f"  {i+1:>2} | {bp:>9.1f}% | {tp:>9.1f}%")
