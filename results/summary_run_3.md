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
| **Mean** | 4387.9 | 5943.5 | **+1555.7** | 767.4 | 982.2 |
| **P95** | 7527.9 | 17954.7 | **+10426.8** | 1144.7 | 1683.8 |
