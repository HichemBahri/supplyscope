# Agent benchmark — llm tier `smart`

**Overall accuracy: 88.4%** (38/43) · first-try 38 · rescued by self-correction 0 · wrong 5 · gave up 0 · median latency 6984.1 ms

| tier | n | accuracy | first-try | rescued | wrong | gave up |
|---|---|---|---|---|---|---|
| easy | 14 | 100.0% | 14 | 0 | 0 | 0 |
| medium | 15 | 86.7% | 13 | 0 | 2 | 0 |
| hard | 14 | 78.6% | 11 | 0 | 3 | 0 |

| topic | n | accuracy |
|---|---|---|
| assets | 2 | 100.0% |
| expert | 2 | 0.0% |
| finance | 4 | 50.0% |
| logistics | 13 | 92.3% |
| ml | 2 | 100.0% |
| procurement | 15 | 100.0% |
| tendering | 5 | 100.0% |

**Self-correction:** 1 questions needed at least one SQL fix; 0 of those ended correct (rescue rate 0.0%).

## Failures

| qid | tier | outcome | reason |
|---|---|---|---|
| H03 | hard | wrong | expected 4, numeric cells seen [0] |
| H10 | hard | wrong | expected entity is absent |
| H13 | hard | wrong | missing entity 'Milano Valvole Industriali' |
| M11 | medium | wrong | expected 7.96249e+06, numeric cells seen [Decimal('7764090.68')] |
| M15 | medium | wrong | expected 15, numeric cells seen [1] |
