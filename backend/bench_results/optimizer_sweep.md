# Optimizer sensitivity sweep

65 policy settings solved (λ ∈ [0.0, 0.15, 0.3, 0.5, 1.0], ceiling ∈ [0.3, 0.9]); 8 on the efficient frontier.

| reference | cash price (TND) | avg p(late) |
|---|---|---|
| actual awards | 26,410,651 | 0.437 |
| naive cheapest | 18,486,644 | 0.354 |
| cheapest policy point | 18,486,644 | 0.354 (λ=0.0, ceiling 0.8) |
| lowest-risk policy point | 21,178,069 | 0.323 (λ=0.0, ceiling 0.6) |

Risk reduction available: 0.354 → 0.323 avg p(late) for +2,691,425 TND (+14.6% cash).

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
