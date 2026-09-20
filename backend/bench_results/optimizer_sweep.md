# Optimizer sensitivity sweep

65 policy settings solved (λ ∈ [0.0, 0.15, 0.3, 0.5, 1.0], ceiling ∈ [0.3, 0.9]); 8 on the efficient frontier.

| reference | cash price (TND) | avg p(late) |
|---|---|---|
| actual awards | 26,410,651 | 0.437 |
| naive cheapest | 18,486,644 | 0.354 |
| cheapest policy point | 18,486,644 | 0.354 (λ=0.0, ceiling 0.8) |
| lowest-risk policy point | 21,178,069 | 0.323 (λ=0.0, ceiling 0.6) |

Risk reduction available: 0.354 → 0.323 avg p(late) for +2,691,425 TND (+14.6% cash).

## Why the 'actual awards' reference is NOT a savings claim

Actual awards that differ from the cheapest FX-normalized bid, and why:

| RFQ | actual bid | cheapest bid | overpaid (TND) | nominal-currency illusion |
|---|---|---|---|---|
| RFQ-2026-0004 | USD 1,867,637 (= 5,789,676 TND) | TND 2,141,049 (= 2,141,049 TND) | 3,648,627 | yes |
| RFQ-2026-0030 | USD 1,288,098 (= 3,993,102 TND) | TND 1,579,868 (= 1,579,868 TND) | 2,413,235 | yes |
| RFQ-2025-0051 | USD 414,966 (= 1,286,396 TND) | TND 516,399 (= 516,399 TND) | 769,996 | yes |
| RFQ-2026-0006 | USD 340,140 (= 1,054,435 TND) | TND 415,429 (= 415,429 TND) | 639,006 | yes |
| RFQ-2026-0029 | USD 159,971 (= 495,911 TND) | TND 212,029 (= 212,029 TND) | 283,882 | yes |
| RFQ-2025-0065 | USD 76,733 (= 237,873 TND) | TND 84,845 (= 84,845 TND) | 153,028 | yes |
| RFQ-2026-0009 | EUR 48,303 (= 164,229 TND) | USD 47,741 (= 147,996 TND) | 16,233 | no |

6 of 7 divergent awards are the simulator's nominal-currency comparison flaw; they account for 7,907,774 of the 7,924,007 TND gap (99.8%). The optimizer 'beats' the simulated history mainly by converting currencies — which real buyers also do. The frontier itself (all points FX-normalized) is unaffected; only the actual-vs-optimizer distance is an artifact.

## Ceiling anatomy (λ = 0.15)

| ceiling | above | enforced | waived | forbidden | diverged | avg p(late) |
|---|---|---|---|---|---|---|
| 0.30 | 42 | 16 | 10 | 16 | 1 | 0.347 |
| 0.35 | 41 | 16 | 10 | 15 | 1 | 0.347 |
| 0.40 | 38 | 18 | 8 | 19 | 3 | 0.339 |
| 0.45 | 33 | 20 | 6 | 19 | 2 | 0.347 |
| 0.50 | 25 | 22 | 4 | 15 | 2 | 0.341 |
| 0.55 | 22 | 24 | 2 | 17 | 3 | 0.328 |
| 0.60 | 18 | 26 | 0 | 18 | 4 | 0.323 |
| 0.65 | 13 | 26 | 0 | 13 | 4 | 0.323 |
| 0.70 | 8 | 26 | 0 | 8 | 2 | 0.338 |
| 0.75 | 4 | 26 | 0 | 4 | 1 | 0.344 |
| 0.80 | 2 | 26 | 0 | 2 | 0 | 0.354 |
| 0.85 | 1 | 26 | 0 | 1 | 0 | 0.354 |
| 0.90 | 0 | 26 | 0 | 0 | 0 | 0.354 |
