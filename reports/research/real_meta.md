# Real META closes: 2016-10-07 to 2026-10-07 (2513 trading days)

Real prices, real gaps, real earnings dates (40 prints). Option prices are modelled: implied vol = the stock's trailing 30-day realized vol (earnings days excluded) × an assumed ratio, plus an 8% earnings move for expiries that span a print. Fills at the ladder cap (worst case).

META went from $128.99 to $721.31. Over the same period the 600 writable shares gained $355,392 — every setting below keeps all of that, because nothing was ever assigned.

## Net yield per year on the 600 writable shares

| Setting | IV 1.0× realized | IV 1.15× | IV 1.3× | Net premium, 10 yrs (1.15×) | Gross premium (1.15×) | Defensive rolls / closes | A / B written | Max shorts | Violations (all 3) |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|
| current (A .15 / B .115) | -0.74% | +1.18% | +1.67% | $22,608 | $264,309 | 12 / 11 | 42% / 38% | 6 | 0 |
| delta 0.10 | -0.71% | +0.46% | +2.13% | $8,760 | $174,552 | 4 / 5 | 43% / 38% | 6 | 0 |
| delta 0.15 | -0.18% | +0.94% | +2.27% | $17,889 | $303,384 | 16 / 18 | 44% / 38% | 6 | 0 |
| delta 0.20 | -0.47% | +0.52% | +2.66% | $9,903 | $419,571 | 22 / 35 | 44% / 38% | 6 | 0 |
| proximity: always close | -1.04% | +0.44% | +1.82% | $8,451 | $222,261 | 0 / 18 | 43% / 37% | 6 | 0 |
| defensive roll cap 0.30Δ | -1.04% | +0.44% | +1.82% | $8,451 | $222,261 | 0 / 18 | 43% / 37% | 6 | 0 |
| 21 DTE: hold if no roll | -0.54% | +1.66% | +2.30% | $31,710 | $281,862 | 19 / 18 | 46% / 40% | 6 | 0 |
| cap 0.30Δ + hold | -0.64% | +0.93% | +2.55% | $17,847 | $219,570 | 0 / 28 | 46% / 39% | 6 | 0 |

## Realized premium by year (IV 1.15×), % of the writable shares' average value

| Year | META | current (A .15 / B .115) | delta 0.10 | delta 0.15 | delta 0.20 | proximity: always close | defensive roll cap 0.30Δ | 21 DTE: hold if no roll | cap 0.30Δ + hold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2016* | -11% | +0.02% | -0.04% | +0.01% | -0.21% | -0.02% | -0.02% | +0.53% | +0.27% |
| 2017 | +51% | +3.23% | +2.30% | +3.36% | +4.01% | +3.23% | +3.23% | +3.67% | +3.67% |
| 2018 | -28% | +2.75% | +3.23% | +3.40% | +2.28% | +2.29% | +2.29% | +4.20% | +3.74% |
| 2019 | +51% | +3.91% | +3.10% | +2.99% | +3.75% | +4.92% | +4.92% | +4.11% | +5.13% |
| 2020 | +30% | -3.75% | -3.83% | -4.11% | -2.55% | -3.75% | -3.75% | -1.94% | -1.94% |
| 2021 | +25% | +0.91% | +0.89% | +0.81% | -1.08% | +0.91% | +0.91% | +2.25% | +3.01% |
| 2022 | -64% | +3.59% | +3.00% | +3.66% | +6.68% | +2.38% | +2.38% | +4.09% | +2.78% |
| 2023 | +184% | -0.20% | -0.76% | +0.61% | -0.69% | -0.20% | -0.20% | -2.30% | -1.91% |
| 2024 | +69% | -4.09% | -1.96% | -6.22% | -8.61% | -5.41% | -5.41% | -2.62% | -4.73% |
| 2025 | +10% | +3.18% | +2.95% | +3.46% | +5.45% | +2.96% | +2.96% | +3.77% | +3.54% |
| 2026* | +11% | +3.22% | -1.15% | +3.29% | +1.00% | +0.96% | +0.96% | +2.52% | +0.50% |

\* partial year (data starts Oct 2016 and ends Oct 2026).

## Earnings check

960 print-checks (40 prints × 8 settings × 3 vol levels). Short calls open inside the 5 trading days before a print: **0**. Biggest next-day move the book sat out: -26.4%.

## Violations

None.
