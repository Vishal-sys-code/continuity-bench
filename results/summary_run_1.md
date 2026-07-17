# Continuity Bench Evaluation Results

## 1. Continuity Preservation Rate (CPR)
*Evaluated exclusively on failover occurrences (N=150 baseline, N=150 treatment).*

| System | CPR (%) | 95% CI |
|---|---|---|
| **Baseline (Stateless)** | 0.0% | [0.0%, 2.5%] |
| **Treatment (History-Forwarding)** | 99.3% | [96.3%, 99.9%] |

## 2. Continuity Latency Overhead (CLO)
*Additional latency incurred by forwarding the full context history during a failover.*

| Metric | Baseline Latency (ms) | Treatment Latency (ms) | CLO (Overhead ms) | Baseline Queue (ms) | Treatment Queue (ms) |
|---|---|---|---|---|---|
| **Mean** | 6489.2 | 4419.0 | **-2070.2** | 943.2 | 773.1 |
| **P95** | 8431.8 | 6269.7 | **-2162.1** | 1603.2 | 1234.8 |
