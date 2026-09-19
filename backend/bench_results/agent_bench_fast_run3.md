# Agent benchmark — llm tier `fast_run3`

**Overall accuracy: 95.3%** (41/43) · first-try 39 · rescued by self-correction 2 · wrong 2 · gave up 0 · median latency 3143.1 ms

| tier | n | accuracy | first-try | rescued | wrong | gave up |
|---|---|---|---|---|---|---|
| easy | 14 | 100.0% | 14 | 0 | 0 | 0 |
| medium | 15 | 93.3% | 13 | 1 | 1 | 0 |
| hard | 14 | 92.9% | 12 | 1 | 1 | 0 |

| topic | n | accuracy |
|---|---|---|
| assets | 2 | 100.0% |
| expert | 2 | 100.0% |
| finance | 4 | 50.0% |
| logistics | 13 | 100.0% |
| ml | 2 | 100.0% |
| procurement | 15 | 100.0% |
| tendering | 5 | 100.0% |

**Self-correction:** 2 questions needed at least one SQL fix; 2 of those ended correct (rescue rate 100.0%).

## Failures

| qid | tier | outcome | reason |
|---|---|---|---|
| H10 | hard | wrong | expected entity is absent |
| M15 | medium | wrong | expected 15, numeric cells seen [1] |
