# Agent benchmark — llm tier `smart_run2`

**Overall accuracy: 93.0%** (40/43) · first-try 40 · rescued by self-correction 0 · wrong 3 · gave up 0 · median latency 6218.2 ms

| tier | n | accuracy | first-try | rescued | wrong | gave up |
|---|---|---|---|---|---|---|
| easy | 14 | 100.0% | 14 | 0 | 0 | 0 |
| medium | 15 | 93.3% | 14 | 0 | 1 | 0 |
| hard | 14 | 85.7% | 12 | 0 | 2 | 0 |

| topic | n | accuracy |
|---|---|---|
| assets | 2 | 100.0% |
| expert | 2 | 100.0% |
| finance | 4 | 50.0% |
| logistics | 13 | 100.0% |
| ml | 2 | 100.0% |
| procurement | 15 | 93.3% |
| tendering | 5 | 100.0% |

**Self-correction:** 0 questions needed at least one SQL fix; 0 of those ended correct (rescue rate None%).

## Failures

| qid | tier | outcome | reason |
|---|---|---|---|
| H01 | hard | wrong | expected 1.495, numeric cells seen [] |
| H10 | hard | wrong | expected entity is absent |
| M15 | medium | wrong | expected 15, numeric cells seen [1] |
