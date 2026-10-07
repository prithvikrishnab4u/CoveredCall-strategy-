# Monte Carlo: 200 random one-year paths per setting

Each path draws its own drift (mean +12%, sd 30%), vol (25-50%), earnings gaps (sd 9%), ~2 news jumps, and an implied/realized vol ratio of 1.0-1.2x. Same paths for every setting. Fills at the ladder cap.

Stock return across paths: median +2%, 10th pct -48%, 90th pct +92%.

| Setting | Median net yield | 10th pct (bad year) | 90th pct (good year) | Paths with net gain | Avg gross premium | Avg defensive rolls | Avg written A / B | Max shorts (any day, any path) | Paths with violations |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| current (A .15 / B .115) | +0.60% | -6.66% | +6.63% | 54% | $71,809 | 1.6 | 43% / 35% | 6 | 0 |
| delta 0.10 | +0.29% | -5.78% | +4.76% | 53% | $50,350 | 1.2 | 44% / 35% | 6 | 0 |
| delta 0.15 | +0.12% | -8.81% | +6.99% | 50% | $80,280 | 1.8 | 44% / 35% | 6 | 0 |
| delta 0.20 | -0.09% | -10.12% | +8.74% | 50% | $119,304 | 3.1 | 44% / 35% | 6 | 0 |
| proximity: always close | +0.10% | -6.60% | +6.35% | 52% | $57,875 | 0.0 | 43% / 35% | 6 | 0 |
| defensive roll cap 0.30Δ | +0.10% | -6.60% | +6.35% | 52% | $57,875 | 0.0 | 43% / 35% | 6 | 0 |
| 21 DTE: hold if no roll | +0.61% | -8.15% | +7.68% | 56% | $81,269 | 2.9 | 47% / 37% | 6 | 0 |
| cap 0.30Δ + hold | +0.97% | -7.02% | +7.27% | 55% | $57,344 | 0.1 | 46% / 37% | 6 | 0 |

## Median net yield by stock outcome

| Stock year | Paths | current (A .15 / B .115) | delta 0.10 | delta 0.15 | delta 0.20 | proximity: always close | defensive roll cap 0.30Δ | 21 DTE: hold if no roll | cap 0.30Δ + hold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| down > 20% | 65 | +4.54% | +3.59% | +5.12% | +6.02% | +4.55% | +4.55% | +4.86% | +5.01% |
| down 0-20% | 31 | +2.39% | +1.99% | +2.87% | +3.32% | +2.39% | +2.39% | +2.90% | +3.11% |
| up 0-20% | 29 | -0.64% | -0.53% | -0.31% | -1.34% | -1.44% | -1.44% | -0.79% | -1.16% |
| up 20-50% | 28 | -1.27% | -0.66% | -2.42% | -2.05% | -1.22% | -1.22% | -0.24% | -0.55% |
| up > 50% | 47 | -6.09% | -4.37% | -6.49% | -6.85% | -6.20% | -6.20% | -6.57% | -5.80% |

## Violations

None across all paths and settings.
