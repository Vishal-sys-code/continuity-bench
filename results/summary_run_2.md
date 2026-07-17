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
| **Mean** | 5904.0 | 6925.0 | **+1021.0** | 722.4 | 814.8 |
| **P95** | 18015.3 | 26157.8 | **+8142.5** | 1099.6 | 1303.2 |
