# Agent benchmark — llm tier `fast`

**Overall accuracy: 88.4%** (38/43) · first-try 36 · rescued by self-correction 2 · wrong 5 · gave up 0 · median latency 3443.7 ms

| tier | n | accuracy | first-try | rescued | wrong | gave up |
|---|---|---|---|---|---|---|
| easy | 14 | 100.0% | 14 | 0 | 0 | 0 |
| medium | 15 | 86.7% | 12 | 1 | 2 | 0 |
| hard | 14 | 78.6% | 10 | 1 | 3 | 0 |

| topic | n | accuracy |
|---|---|---|
| assets | 2 | 100.0% |
| expert | 2 | 0.0% |
| finance | 4 | 50.0% |
| logistics | 13 | 92.3% |
| ml | 2 | 100.0% |
| procurement | 15 | 100.0% |
| tendering | 5 | 100.0% |

**Self-correction:** 2 questions needed at least one SQL fix; 2 of those ended correct (rescue rate 100.0%).

## Failures

| qid | tier | outcome | reason |
|---|---|---|---|
| H03 | hard | wrong | expected 4, numeric cells seen [0] |
| H10 | hard | wrong | expected entity is absent |
| H13 | hard | wrong | expected 3 rows, got 2 |
| M11 | medium | wrong | expected 7.96249e+06, numeric cells seen [Decimal('7764090.68')] |
| M15 | medium | wrong | expected 15, numeric cells seen [1] |
