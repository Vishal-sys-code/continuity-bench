# Continuity Bench Evaluation Results

## 1. Continuity Preservation Rate (CPR)
*Evaluated exclusively on failover occurrences (N=150 baseline, N=150 treatment).*

| System | CPR (%) | 95% CI |
|---|---|---|
| **Baseline (Stateless)** | 0.0% | [0.0%, 2.5%] |
| **Treatment (History-Forwarding)** | 98.7% | [95.3%, 99.6%] |

## 2. Continuity Latency Overhead (CLO)
*Additional latency incurred by forwarding the full context history during a failover.*

| Metric | Baseline Latency (ms) | Treatment Latency (ms) | CLO (Overhead ms) | Baseline Queue (ms) | Treatment Queue (ms) |
|---|---|---|---|---|---|
| **Mean** | 8593.5 | 4157.3 | **-4436.2** | 724.5 | 784.9 |
| **P95** | 34027.3 | 8622.0 | **-25405.3** | 1043.2 | 1298.9 |
