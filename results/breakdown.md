# Subgroup Breakdown and Negative Results
*Aggregated across all runs to highlight performance degradation in specific edge cases.*

## Detailed Subgroup Metrics

|Length Bucket|Provider|Concurrency|N|Treatment CPR (%)|Baseline Lat (ms)|Treatment Lat (ms)|CLO (ms)|
|---|---|---|---|---|---|---|---|
|11+ turns|openai|100|240|100.0%|1526.9|1250.2|-276.7|
|6-10 turns|openai|100|510|100.0%|1557.5|1291.5|-266.0|

## ⚠️ Candidate Negative Results
*Subgroups explicitly flagged where Treatment CPR < 70% or Treatment Latency > 2x Baseline.*

✅ **No negative results detected.** All subgroups maintained >=70% CPR and <2x latency overhead.
