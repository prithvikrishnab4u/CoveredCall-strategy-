# Regime tests and delta sweep

Fills assumed at the ladder cap (worst case). Yield = annualized premium ÷ average value of the 600 writable shares. Defensive = proximity or ex-div rule fired.

| Regime | Delta | Spot | Gross premium | Net premium | Net yield | Defensive rolls | Defensive closes | A / B written | Max shorts | Violations |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| bull_+40%_6mo | current (A .15 / B .115) | 650→942 | $66,750 | $9,084 | +1.8% | 2 | 2 | 40% / 35% | 6 | 0 |
| bull_+40%_6mo | delta 0.10 | 650→942 | $54,693 | $6,297 | +1.3% | 1 | 2 | 44% / 34% | 6 | 0 |
| bull_+40%_6mo | delta 0.15 | 650→942 | $65,805 | $11,520 | +2.3% | 1 | 2 | 43% / 36% | 6 | 0 |
| bull_+40%_6mo | delta 0.20 | 650→942 | $88,545 | $25,005 | +5.0% | 1 | 2 | 43% / 38% | 6 | 0 |
| bear_-50% | current (A .15 / B .115) | 650→344 | $62,265 | $14,565 | +4.9% | 2 | 0 | 41% / 36% | 6 | 0 |
| bear_-50% | delta 0.10 | 650→344 | $31,005 | $9,996 | +3.3% | 1 | 0 | 43% / 31% | 6 | 0 |
| bear_-50% | delta 0.15 | 650→344 | $68,925 | $12,129 | +4.0% | 2 | 1 | 41% / 39% | 6 | 0 |
| bear_-50% | delta 0.20 | 650→344 | $83,715 | $17,643 | +5.9% | 2 | 2 | 43% / 37% | 6 | 0 |
| earnings_gap_+12% | current (A .15 / B .115) | 650→878 | $80,385 | -$7,734 | -1.6% | 4 | 3 | 42% / 34% | 6 | 0 |
| earnings_gap_+12% | delta 0.10 | 650→878 | $41,844 | -$2,391 | -0.5% | 1 | 0 | 45% / 33% | 6 | 0 |
| earnings_gap_+12% | delta 0.15 | 650→878 | $77,490 | -$9,792 | -2.1% | 3 | 3 | 47% / 33% | 6 | 0 |
| earnings_gap_+12% | delta 0.20 | 650→878 | $114,255 | -$11,169 | -2.4% | 6 | 4 | 45% / 33% | 6 | 0 |
| earnings_moved_up_+12% | current (A .15 / B .115) | 650→878 | $111,795 | $20,577 | +4.2% | 5 | 0 | 62% / 61% | 6 | 0 |
| earnings_moved_up_+12% | delta 0.10 | 650→878 | $65,127 | $10,410 | +2.1% | 1 | 0 | 64% / 61% | 6 | 0 |
| earnings_moved_up_+12% | delta 0.15 | 650→878 | $143,580 | $19,161 | +3.9% | 8 | 1 | 66% / 61% | 6 | 0 |
| earnings_moved_up_+12% | delta 0.20 | 650→878 | $165,855 | $30,351 | +6.1% | 6 | 3 | 63% / 54% | 6 | 0 |
| sideways_chop | current (A .15 / B .115) | 650→650 | $39,327 | $14,493 | +3.8% | 0 | 0 | 41% / 35% | 6 | 0 |
| sideways_chop | delta 0.10 | 650→650 | $33,729 | $11,154 | +2.9% | 1 | 0 | 44% / 35% | 6 | 0 |
| sideways_chop | delta 0.15 | 650→650 | $45,495 | $17,409 | +4.6% | 0 | 0 | 41% / 36% | 6 | 0 |
| sideways_chop | delta 0.20 | 650→650 | $79,395 | $13,221 | +3.5% | 2 | 2 | 45% / 38% | 6 | 0 |

## Earnings audit (current settings)

Short calls open at any close inside the 5 trading days before each print must be 0.

| Regime | Print | Engine believed (10 days prior) | Max shorts in 5-day window | Closed by earnings rule | Next-day gap |
|---|---|---|---:|---:|---:|
| bull_+40%_6mo | 2026-01-28 | 2026-01-28 | 0 | 0 | -0.7% |
| bull_+40%_6mo | 2026-04-29 | 2026-04-29 | 0 | 0 | +3.2% |
| bull_+40%_6mo | 2026-07-29 | 2026-07-29 | 0 | 0 | +0.9% |
| bull_+40%_6mo | 2026-10-28 | 2026-10-28 | 0 | 0 | -0.8% |
| bear_-50% | 2026-01-28 | 2026-01-28 | 0 | 0 | +1.4% |
| bear_-50% | 2026-04-29 | 2026-04-29 | 0 | 0 | -8.2% |
| bear_-50% | 2026-07-29 | 2026-07-29 | 0 | 0 | -2.4% |
| bear_-50% | 2026-10-28 | 2026-10-28 | 0 | 0 | +0.2% |
| earnings_gap_+12% | 2026-01-28 | 2026-01-28 | 0 | 0 | +12.2% |
| earnings_gap_+12% | 2026-04-29 | 2026-04-29 | 0 | 0 | +9.3% |
| earnings_gap_+12% | 2026-07-29 | 2026-07-29 | 0 | 0 | +9.4% |
| earnings_gap_+12% | 2026-10-28 | 2026-10-28 | 0 | 0 | +13.7% |
| earnings_moved_up_+12% | 2026-01-07 | None | 0 | 0 | +8.0% |
| earnings_moved_up_+12% | 2026-04-08 | 2026-04-29 (moved) | 0 | 0 | +12.2% |
| earnings_moved_up_+12% | 2026-07-08 | 2026-07-29 (moved) | 0 | 0 | +15.1% |
| earnings_moved_up_+12% | 2026-10-07 | 2026-10-28 (moved) | 0 | 0 | +13.4% |
| sideways_chop | 2026-01-28 | 2026-01-28 | 0 | 0 | -2.2% |
| sideways_chop | 2026-04-29 | 2026-04-29 | 0 | 0 | +0.3% |
| sideways_chop | 2026-07-29 | 2026-07-29 | 0 | 0 | +1.1% |
| sideways_chop | 2026-10-28 | 2026-10-28 | 0 | 0 | +1.8% |

## Moved-earnings stress: 40 random paths per setting

Each print lands 3 weeks before the estimate the engine was using, and the real date is announced only 10 days ahead, so contracts opened or rolled under the estimate can be open into the real print. The 5-day close rule is the backstop.

| Setting | Prints | Prints with calls open when the date moved | Closed by the 5-day rule | Short calls open inside the 5-day window | Violations |
|---|---:|---:|---:|---:|---:|
| current (A .15 / B .115) | 120 | 0 | 0 | 0 | 0 |
| delta 0.10 | 120 | 0 | 0 | 0 | 0 |
| delta 0.15 | 120 | 0 | 0 | 0 | 0 |
| delta 0.20 | 120 | 0 | 0 | 0 | 0 |
| proximity: always close | 120 | 0 | 0 | 0 | 0 |
| defensive roll cap 0.30Δ | 120 | 0 | 0 | 0 | 0 |
| 21 DTE: hold if no roll | 120 | 22 | 25 | 0 | 0 |
| cap 0.30Δ + hold | 120 | 23 | 26 | 0 | 0 |

## Violations

None in any regime or delta setting.
