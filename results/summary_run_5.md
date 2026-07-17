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
| **Mean** | 6224.6 | 6283.2 | **+58.5** | 806.8 | 798.8 |
| **P95** | 18224.9 | 17584.4 | **-640.5** | 1262.0 | 1212.6 |
