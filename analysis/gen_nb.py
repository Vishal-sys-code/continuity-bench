import json
from pathlib import Path

cells = []
def add_md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": [line + "\n" for line in text.split("\n")]})
def add_code(text):
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [line + "\n" for line in text.split("\n")]})

add_md("# Continuity-Bench Results Analysis\nThis notebook loads the raw metrics from the evaluation pipeline and generates summary visualizations.")

add_code("""import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import json
import math
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path('.').resolve().parent
RESULTS_DIR = PROJECT_ROOT / 'results'
FIG_DIR = RESULTS_DIR / 'figures'
FIG_DIR.mkdir(exist_ok=True, parents=True)

# Set plotting style
sns.set_theme(style='whitegrid')
plt.rcParams['figure.figsize'] = (8, 5)""")

add_md("## 1. Data Loading\nLoad the raw metrics and merge in the conversation length from the testsuite.")

add_code("""# Load raw metrics
df = pd.read_csv(RESULTS_DIR / 'raw_metrics.csv')
# Filter to only failover turns (where continuity preservation matters)
df = df[df['failed_over'] == True].copy()
df['preserved'] = df['preserved'].astype(bool)

# Load conversations to get turn counts
with open(PROJECT_ROOT / 'testsuite' / 'conversations.json', 'r', encoding='utf-8') as f:
    conversations = json.load(f)
    
turn_counts = {c['id']: len(c['turns']) for c in conversations}
df['turn_count'] = df['conversation_id'].map(turn_counts)

# Bin into Short (<=4), Medium (5), Long (>=6)
def categorize_length(n):
    if n <= 4: return 'Short (<=4)'
    if n == 5: return 'Medium (5)'
    return 'Long (>=6)'

df['length_category'] = df['turn_count'].apply(categorize_length)
print(f'Loaded {len(df)} failover records.')""")

add_md("## 2. Continuity Preservation Rate (CPR)")

add_code("""def wilson_ci(successes, n, z=1.96):
    if n == 0: return 0.0
    p = successes / n
    denominator = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    adj_std = math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    lower = (center - z * adj_std) / denominator
    upper = (center + z * adj_std) / denominator
    return max(0, lower), min(1, upper)

# Calculate CPR per system
cpr_data = []
for sys_name in df['system'].unique():
    subset = df[df['system'] == sys_name]
    n = len(subset)
    succ = subset['preserved'].sum()
    rate = succ / n if n > 0 else 0
    lower, upper = wilson_ci(succ, n)
    cpr_data.append({
        'System': sys_name.title(),
        'CPR': rate,
        'Yerr_Lower': rate - lower,
        'Yerr_Upper': upper - rate
    })

cpr_df = pd.DataFrame(cpr_data)

# Plot
plt.figure(figsize=(7, 5))
bars = plt.bar(cpr_df['System'], cpr_df['CPR'] * 100, 
               yerr=[cpr_df['Yerr_Lower'] * 100, cpr_df['Yerr_Upper'] * 100],
               capsize=10, color=['#e74c3c', '#2ecc71'], alpha=0.8)

plt.title('Continuity Preservation Rate (CPR) by System\\n(Failover Scenarios)', fontsize=14)
plt.ylabel('Preservation Rate (%)', fontsize=12)
plt.ylim(0, 110)

# Add value labels
for bar in bars:
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval + 5, f'{yval:.1f}%', ha='center', va='bottom', fontweight='bold')

plt.tight_layout()
plt.savefig(FIG_DIR / 'cpr_comparison.png', dpi=300)
plt.show()""")

add_md("## 3. Continuity Latency Overhead (CLO)")

add_code("""plt.figure(figsize=(8, 5))
sns.kdeplot(data=df, x='latency_ms', hue='system', fill=True, common_norm=False, 
            palette={'baseline': '#e74c3c', 'treatment': '#2ecc71'}, alpha=0.5)

# Calculate mean and p95
base_lats = df[df['system'] == 'baseline']['latency_ms']
treat_lats = df[df['system'] == 'treatment']['latency_ms']

if not base_lats.empty and not treat_lats.empty:
    plt.axvline(base_lats.mean(), color='#c0392b', linestyle='--', label=f'Baseline Mean: {base_lats.mean():.0f}ms')
    plt.axvline(treat_lats.mean(), color='#27ae60', linestyle='--', label=f'Treatment Mean: {treat_lats.mean():.0f}ms')

plt.title('Continuity Latency Overhead (CLO) Distribution', fontsize=14)
plt.xlabel('Failover Latency (ms)', fontsize=12)
plt.ylabel('Density', fontsize=12)
plt.legend()
plt.tight_layout()
plt.savefig(FIG_DIR / 'latency_distribution.png', dpi=300)
plt.show()""")

add_md("## 4. CPR Breakdown by Conversation Length")

add_code("""length_cpr = df.groupby(['system', 'length_category']).apply(
    lambda x: pd.Series({
        'CPR': x['preserved'].mean(),
        'N': len(x)
    })
).reset_index()

plt.figure(figsize=(9, 5))
sns.barplot(data=length_cpr, x='length_category', y='CPR', hue='system',
            order=['Short (<=4)', 'Medium (5)', 'Long (>=6)'],
            palette={'baseline': '#e74c3c', 'treatment': '#2ecc71'})

plt.title('CPR by Conversation Length', fontsize=14)
plt.xlabel('Conversation Length (Turns)', fontsize=12)
plt.ylabel('Preservation Rate (0-1)', fontsize=12)
plt.ylim(0, 1.1)
plt.legend(title='System')
plt.tight_layout()
plt.savefig(FIG_DIR / 'cpr_by_length.png', dpi=300)
plt.show()""")


nb = {
    "cells": cells,
    "metadata": {},
    "nbformat": 4,
    "nbformat_minor": 5
}

out_path = Path("analysis/results.ipynb")
out_path.parent.mkdir(exist_ok=True, parents=True)
with open(out_path, "w") as f:
    json.dump(nb, f, indent=2)
print("Generated analysis/results.ipynb successfully!")
