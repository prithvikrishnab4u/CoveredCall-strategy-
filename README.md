# META Covered Call Manager

A rule-driven system for selling covered calls on 900 META shares, built so the
shares are never called away.

**Status: steps 1–2 of 5.** The rules engine and the replay are done. Nothing
here talks to Schwab or Telegram yet, and nothing can place an order.

| Step | What | Status |
|---|---|---|
| 1 | Rules engine + unit tests | Done |
| 2 | Replay over simulated option chains | Done |
| 3 | Read-only Schwab connection, broker reconciliation | Next |
| 4 | ALERT mode loop + Telegram | |
| 5 | LIVE mode with Telegram Approve/Reject | |

## Quick start

```bash
pip install -r requirements.txt
python -m pytest                          # 81 tests
python -m meta_covered_calls.replay       # all scenarios, writes reports/
python -m meta_covered_calls.replay --scenario melt_up --fill cap
```

Replay real closes from a CSV (`date,close`) instead of the built-in paths:

```bash
python -m meta_covered_calls.replay --csv meta_closes.csv \
  --earnings 2025-01-29,2025-04-30,2025-07-30,2025-10-29 \
  --ex-div 2025-03-14,2025-06-16,2025-09-22,2025-12-15
```

## The rulebook

All numbers live in `meta_covered_calls/config.py`.

**Tranches**

| Tranche | Contracts | DTE | Delta |
|---|---|---|---|
| A | 3 | 28–35 | 0.14–0.16 |
| B | 3 | 40–49 | 0.10–0.13 |
| C | 0 | never written | |

Hard cap: never more than 6 short calls in total, so Tranche C's 300 shares can't be encumbered even by a bug.

**Opening a contract** (idle tranche only)
- Expiry: any Friday weekly inside the tranche's DTE band.
- Expiry must be at least 14 calendar days before the next earnings date.
- Nothing opens until 2 full trading sessions have passed after earnings.
- If the earnings date is unknown, nothing opens and an alert goes out.

**Managing an open contract.** Rules are checked in this order, and the first match wins:

| # | Rule | Condition | Action |
|---|---|---|---|
| 0 | Earnings window | ≤ 5 trading days to earnings | Close, whatever the P&L |
| 1 | Ex-div guard | ≤ 3 trading days to ex-div, and time value < dividend + $0.15 | Roll out, else close |
| 2 | Proximity | spot ≥ 98% of strike | Roll up and out for credit, else close |
| 3 | Profit target | ≥ 50% of the credit captured | Close |
| 4 | Time stop | ≤ 21 DTE | ≥ 40% profit: close. Otherwise: roll, else close |

**Rolls**
- Each roll goes in as a single two-leg net-credit order. It must be credit or flat at the worst price the ladder will accept.
- First choice: 30–45 DTE, clearing the 14-day earnings blackout.
- If that's blocked: 14+ DTE, expiring at least 5 trading days before earnings (an "earnings-buffer roll").
- New strike: at or above the old strike, and outside the 2% proximity band, so the roll doesn't trigger again the next day.
- If no roll works: close the position.

**Order ladder**
- Start at mid and step $0.05 every 30 seconds toward the natural price.
- Stop at 60% of the bid–ask spread (measured from the side that favors you).
- If nothing fills by then, the order is left pending and an alert goes out (step 4).

**Safety validator** (`safety.py`)
- Re-checks every decision independently of the engine: symbol, quantity == 3, allowed instructions, no writing on C, the 6-contract cap, earnings rules, closes matching the held contract, no debit rolls.
- Any failure raises an error and nothing proceeds.

## Interpretations worth knowing

These are choices I made where the spec left room. Each is a config value or a few lines of code to change.

1. **Earnings timing.** Earnings is assumed to be after the close (META's pattern). "Days to earnings" counts trading sessions after today, up to and including the earnings day.
2. **Ex-div guard on cheap out-of-the-money calls.** As specified, the guard compares time value to $0.68 for any call, so it also fires on cheap out-of-the-money calls that carry almost no real early-assignment risk. That costs little (a small buyback), but it's a choice. It can be limited to calls near the money.
3. **Proximity rolls land at 0.37–0.45 delta.** When spot is within 2% of the strike, a credit-only roll can't move the strike far. The new contract is safer than the old one, but still fairly close to the money. **Open question:** cap the roll delta (say ≤ 0.30) and close if the cap can't be met?
4. **21 DTE roll target.** The strike nearest the tranche's target delta, never above the tranche's maximum delta. I tested dropping that cap and the results were mixed, so the cap stays.
5. **Profit %.** Measured on the current contract's own credit. The cumulative credit across a chain of rolls is tracked separately for reporting.

## What the replay shows

`reports/summary.md` covers 9 scenarios × 2 fill assumptions (fills at mid, and fills at the ladder cap):

- **Zero rule violations.** In every scenario, nothing was assigned and no call was held through earnings. No call was in the money in expiration week, none was exposed to early assignment before ex-div, there were never more than 6 short calls, and Tranche C was never written.
- **Shares are written about 45% (A) and 30–40% (B) of the time.** This is the earnings blackout's cost. In the second half of each quarter there's often no legal expiry, especially for B.
- **Calm and choppy markets give modest income.** Wins at the 50% target are small (about $700–900 per 3 contracts). Most of the drag comes from 21 DTE positions that can't be rolled for a credit and get closed at a loss.
- **Strong rallies cost money in premium:** about −$55k to −$75k in the melt-up and news-gap paths. Every defensive action is a buyback. Over the same paths the 900 shares gained $600k+, so this is the price of never being assigned.

**Caveats.** The chains come from Black-Scholes, not real market data. The engine is checked once per day at the close, while the live system will check every 30 minutes. Earnings and ex-div dates are placeholders in META's usual rhythm. Treat the dollar figures as directional. The rule-safety results are the solid part.

## Research runs

```bash
python -m meta_covered_calls.research regimes      # bull/bear/earnings regimes x delta sweep + earnings audit
python -m meta_covered_calls.research montecarlo --paths 200
python -m meta_covered_calls.research history      # 12-year stylized path (slow: ~15 min)
```

Reports in `reports/research/`. Every setting is compared on the same paths:

- **Delta sweep:** both tranches at 0.10, 0.15, or 0.20.
- **Policy variants:**
  - Proximity always closes.
  - Defensive rolls capped at 0.30 delta.
  - At 21 DTE, hold instead of closing when no credit roll exists.

To test another rule, add a `StrategyConfig` to `VARIANTS` or `POLICIES` in `research/__main__.py`.

Main findings, all on synthetic data:
- Zero rule violations across about 2,000 runs.
- Net income is roughly break-even on average. It's positive in down and flat years and negative in strong up years. Refusing assignment turns every big rally into a cash buyback.
- Higher delta means more gross premium but worse net results.

## Tax note: for your CPA, not code

Under the qualified covered call rules, calls with 30 days or less to expiry generally don't qualify. Tranche A (28–35 DTE) and the earnings-buffer rolls can land there. The straddle rules can then defer losses on the calls. Ask your CPA how this affects buyback losses in this account.

## Layout

```
meta_covered_calls/
  config.py            every rule's number
  models.py            quotes, chains, positions, decisions, order tickets
  market_calendar.py   NYSE trading days and holidays
  pricing.py           profit %, time value, reprice ladder
  strategy_engine.py   the rulebook (pure: no I/O)
  safety.py            independent checks on every decision
  state_store.py       tranche state, fills, JSON persistence
  replay/              synthetic chains, scenarios, day-by-day runner
  research/            regimes, delta/policy sweeps, Monte Carlo, long history
tests/                 81 tests
reports/               sample replay output
```
