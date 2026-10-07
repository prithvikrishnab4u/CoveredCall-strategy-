# Replay summary

Synthetic Black-Scholes chains, one evaluation per day at the close. Earnings/ex-div dates are placeholders. Premium is net of all buybacks, with any still-open contract marked at mid.

| Scenario | Fill | Spot start → end | Net premium | Closes | Rolls | Opens | A / B days written | Violations |
|---|---|---|---:|---:|---:|---:|---|---:|
| steady_grind | mid | 650 → 971 | $-1,478 | 26 | 5 | 26 | 45% / 32% | 0 |
| steady_grind | cap | 650 → 971 | $-1,458 | 26 | 5 | 26 | 45% / 32% | 0 |
| chop | mid | 650 → 561 | $5,223 | 25 | 3 | 25 | 43% / 32% | 0 |
| chop | cap | 650 → 561 | $5,289 | 25 | 3 | 25 | 43% / 32% | 0 |
| rally_into_strikes | mid | 650 → 568 | $11,324 | 26 | 4 | 26 | 46% / 39% | 0 |
| rally_into_strikes | cap | 650 → 568 | $11,391 | 26 | 4 | 26 | 46% / 39% | 0 |
| earnings_gap_up | mid | 650 → 1450 | $7,740 | 31 | 3 | 31 | 44% / 39% | 0 |
| earnings_gap_up | cap | 650 → 1450 | $7,671 | 31 | 3 | 31 | 44% / 39% | 0 |
| earnings_gap_down | mid | 650 → 397 | $-4,598 | 28 | 4 | 28 | 44% / 31% | 0 |
| earnings_gap_down | cap | 650 → 397 | $-4,584 | 28 | 4 | 28 | 44% / 31% | 0 |
| news_gap_up | mid | 650 → 1424 | $-74,254 | 27 | 6 | 27 | 41% / 39% | 0 |
| news_gap_up | cap | 650 → 1424 | $-74,709 | 27 | 6 | 27 | 41% / 39% | 0 |
| rally_into_ex_div | mid | 650 → 1120 | $-20,752 | 20 | 4 | 20 | 46% / 37% | 0 |
| rally_into_ex_div | cap | 650 → 1120 | $-20,829 | 20 | 4 | 20 | 46% / 37% | 0 |
| selloff_then_recovery | mid | 650 → 1076 | $3,426 | 25 | 5 | 25 | 41% / 30% | 0 |
| selloff_then_recovery | cap | 650 → 1076 | $3,228 | 24 | 4 | 24 | 41% / 30% | 0 |
| melt_up | mid | 650 → 1363 | $-55,083 | 34 | 8 | 34 | 47% / 31% | 0 |
| melt_up | cap | 650 → 1363 | $-55,398 | 34 | 8 | 34 | 47% / 31% | 0 |

## Exits by reason

- **steady_grind** (mid): CLOSE:PROFIT_TARGET 17, CLOSE:PROXIMITY 1, CLOSE:TIME_STOP_ROLL 8, OPEN:NEW_ENTRY 26, ROLL:PROXIMITY 2, ROLL:TIME_STOP_ROLL 3
- **steady_grind** (cap): CLOSE:PROFIT_TARGET 17, CLOSE:PROXIMITY 1, CLOSE:TIME_STOP_ROLL 8, OPEN:NEW_ENTRY 26, ROLL:PROXIMITY 2, ROLL:TIME_STOP_ROLL 3
- **chop** (mid): CLOSE:PROFIT_TARGET 19, CLOSE:PROXIMITY 1, CLOSE:TIME_STOP_ROLL 5, OPEN:NEW_ENTRY 25, ROLL:PROXIMITY 1, ROLL:TIME_STOP_ROLL 2
- **chop** (cap): CLOSE:PROFIT_TARGET 19, CLOSE:PROXIMITY 1, CLOSE:TIME_STOP_ROLL 5, OPEN:NEW_ENTRY 25, ROLL:PROXIMITY 1, ROLL:TIME_STOP_ROLL 2
- **rally_into_strikes** (mid): CLOSE:PROFIT_TARGET 18, CLOSE:TIME_STOP_PROFIT 2, CLOSE:TIME_STOP_ROLL 6, OPEN:NEW_ENTRY 26, ROLL:TIME_STOP_ROLL 4
- **rally_into_strikes** (cap): CLOSE:PROFIT_TARGET 18, CLOSE:TIME_STOP_PROFIT 2, CLOSE:TIME_STOP_ROLL 6, OPEN:NEW_ENTRY 26, ROLL:TIME_STOP_ROLL 4
- **earnings_gap_up** (mid): CLOSE:PROFIT_TARGET 24, CLOSE:PROXIMITY 1, CLOSE:TIME_STOP_PROFIT 1, CLOSE:TIME_STOP_ROLL 5, OPEN:NEW_ENTRY 31, ROLL:PROXIMITY 1, ROLL:TIME_STOP_ROLL 2
- **earnings_gap_up** (cap): CLOSE:PROFIT_TARGET 24, CLOSE:PROXIMITY 1, CLOSE:TIME_STOP_PROFIT 1, CLOSE:TIME_STOP_ROLL 5, OPEN:NEW_ENTRY 31, ROLL:PROXIMITY 1, ROLL:TIME_STOP_ROLL 2
- **earnings_gap_down** (mid): CLOSE:PROFIT_TARGET 23, CLOSE:PROXIMITY 4, CLOSE:TIME_STOP_ROLL 1, OPEN:NEW_ENTRY 28, ROLL:PROXIMITY 2, ROLL:TIME_STOP_ROLL 2
- **earnings_gap_down** (cap): CLOSE:PROFIT_TARGET 23, CLOSE:PROXIMITY 4, CLOSE:TIME_STOP_ROLL 1, OPEN:NEW_ENTRY 28, ROLL:PROXIMITY 2, ROLL:TIME_STOP_ROLL 2
- **news_gap_up** (mid): CLOSE:PROFIT_TARGET 15, CLOSE:PROXIMITY 7, CLOSE:TIME_STOP_ROLL 5, OPEN:NEW_ENTRY 27, ROLL:PROXIMITY 5, ROLL:TIME_STOP_ROLL 1
- **news_gap_up** (cap): CLOSE:PROFIT_TARGET 15, CLOSE:PROXIMITY 7, CLOSE:TIME_STOP_ROLL 5, OPEN:NEW_ENTRY 27, ROLL:PROXIMITY 5, ROLL:TIME_STOP_ROLL 1
- **rally_into_ex_div** (mid): CLOSE:PROFIT_TARGET 11, CLOSE:PROXIMITY 2, CLOSE:TIME_STOP_PROFIT 1, CLOSE:TIME_STOP_ROLL 6, OPEN:NEW_ENTRY 20, ROLL:PROXIMITY 1, ROLL:TIME_STOP_ROLL 3
- **rally_into_ex_div** (cap): CLOSE:PROFIT_TARGET 11, CLOSE:PROXIMITY 2, CLOSE:TIME_STOP_PROFIT 1, CLOSE:TIME_STOP_ROLL 6, OPEN:NEW_ENTRY 20, ROLL:PROXIMITY 1, ROLL:TIME_STOP_ROLL 3
- **selloff_then_recovery** (mid): CLOSE:PROFIT_TARGET 20, CLOSE:PROXIMITY 2, CLOSE:TIME_STOP_PROFIT 2, CLOSE:TIME_STOP_ROLL 1, OPEN:NEW_ENTRY 25, ROLL:PROXIMITY 3, ROLL:TIME_STOP_ROLL 2
- **selloff_then_recovery** (cap): CLOSE:PROFIT_TARGET 18, CLOSE:PROXIMITY 2, CLOSE:TIME_STOP_PROFIT 2, CLOSE:TIME_STOP_ROLL 2, OPEN:NEW_ENTRY 24, ROLL:PROXIMITY 2, ROLL:TIME_STOP_ROLL 2
- **melt_up** (mid): CLOSE:PROFIT_TARGET 23, CLOSE:PROXIMITY 7, CLOSE:TIME_STOP_ROLL 4, OPEN:NEW_ENTRY 34, ROLL:PROXIMITY 5, ROLL:TIME_STOP_ROLL 3
- **melt_up** (cap): CLOSE:PROFIT_TARGET 23, CLOSE:PROXIMITY 7, CLOSE:TIME_STOP_ROLL 4, OPEN:NEW_ENTRY 34, ROLL:PROXIMITY 5, ROLL:TIME_STOP_ROLL 3

## Violations

None. No assignment, no call held through earnings, no ITM call in expiration week, no early-assignment exposure before ex-div, never more than 6 short calls, Tranche C never written.
