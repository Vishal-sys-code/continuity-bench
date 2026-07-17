# Continuity Bench: Phase 2 Statistical Analysis
*Runs: 5 | Concurrency: 100 | Total Conversations: 750*

## 1. Continuity Preservation Rate (CPR)
*Wilson Score Intervals (95% CI) computed on pooled failover occurrences.*

| System | Total Failovers | Preserved | CPR (%) | 95% CI (Wilson) |
|---|---|---|---|---|
| **Baseline** | 750 | 0 | 0.0% | [0.0%, 0.5%] |
| **Treatment** | 750 | 750 | 100.0% | [99.5%, 100.0%] |

## 2. Continuity Latency Overhead (CLO)
*Paired differences (Treatment - Baseline). 95% CIs computed via bootstrap (1000 resamples).*

| Metric | Point Estimate (ms) | 95% CI (Bootstrap) |
|---|---|---|
| **Mean CLO** | -269.4 | [-360.1, -169.4] |
| **Median CLO** | -275.8 | [-299.1, -257.4] |
| **P95 CLO** | +734.6 | [+358.1, +1453.8] |

## 3. Run-to-Run Variance
*Independent metrics across the 5 separate runs to assess system jitter under load.*

| Run ID | Baseline CPR (%) | Treatment CPR (%) | Mean CLO (ms) |
|---|---|---|---|
| Run 1 | 0.0% | 100.0% | -320.0 |
| Run 2 | 0.0% | 100.0% | -227.0 |
| Run 3 | 0.0% | 100.0% | -180.8 |
| Run 4 | 0.0% | 100.0% | -225.5 |
| Run 5 | 0.0% | 100.0% | -393.7 |

**Treatment CPR StdDev:** 0.0%
**Mean CLO StdDev:** 76.9ms
