"""Run the replay from the command line.

    python -m meta_covered_calls.replay                      # all built-in scenarios
    python -m meta_covered_calls.replay --scenario melt_up --fill cap
    python -m meta_covered_calls.replay --csv closes.csv --earnings 2026-01-28,2026-04-29 \\
        --ex-div 2026-03-16,2026-06-15
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from .runner import ReplayResult, run_replay
from .scenarios import builtin_scenarios, load_csv_scenario


def _dates(s: str) -> list[date]:
    return [date.fromisoformat(x.strip()) for x in s.split(",") if x.strip()]


def _write_events(result: ReplayResult, out: Path) -> Path:
    path = out / f"{result.scenario.name}_{result.fill_mode}_events.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "tranche", "action", "reason", "cash", "spot", "message"])
        for e in result.events:
            w.writerow([e.day, e.tranche, e.action, e.reason, f"{e.cash:.2f}", f"{e.spot:.2f}", e.message])
    return path


def _summary_md(results: list[ReplayResult]) -> str:
    lines = [
        "# Replay summary",
        "",
        "Synthetic Black-Scholes chains, one evaluation per day at the close. "
        "Earnings/ex-div dates are placeholders. Premium is net of all buybacks, "
        "with any still-open contract marked at mid.",
        "",
        "| Scenario | Fill | Spot start → end | Net premium | Closes | Rolls | Opens | A / B days written | Violations |",
        "|---|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for r in results:
        closes = sorted(r.scenario.closes)
        s0, s1 = r.scenario.closes[closes[0]], r.scenario.closes[closes[-1]]
        acts = [e.action for e in r.events]
        a = r.encumbered_days["A"] / r.trading_days
        b = r.encumbered_days["B"] / r.trading_days
        lines.append(
            f"| {r.scenario.name} | {r.fill_mode} | {s0:.0f} → {s1:.0f} | ${r.net_premium:,.0f} | "
            f"{acts.count('CLOSE')} | {acts.count('ROLL')} | {acts.count('OPEN')} | {a:.0%} / {b:.0%} | "
            f"{len(r.violations)} |"
        )
    lines += ["", "## Exits by reason", ""]
    for r in results:
        counts = ", ".join(f"{k} {v}" for k, v in sorted(r.counts().items()))
        lines.append(f"- **{r.scenario.name}** ({r.fill_mode}): {counts}")
    bad = [r for r in results if r.violations]
    lines += ["", "## Violations", ""]
    if not bad:
        lines.append("None. No assignment, no call held through earnings, no ITM call in expiration week, "
                     "no early-assignment exposure before ex-div, never more than 6 short calls, Tranche C never written.")
    for r in bad:
        lines.append(f"### {r.scenario.name}")
        lines += [f"- {v}" for v in r.violations]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m meta_covered_calls.replay")
    p.add_argument("--scenario", default="all", help="built-in scenario name, or 'all'")
    p.add_argument("--fill", choices=["mid", "cap", "both"], default="both",
                   help="assume fills at mid, at the ladder cap (worst case), or run both")
    p.add_argument("--out", default="reports", help="output folder")
    p.add_argument("--csv", help="replay real closes from a date,close CSV instead")
    p.add_argument("--earnings", default="", help="comma-separated earnings dates (with --csv)")
    p.add_argument("--ex-div", default="", help="comma-separated ex-dividend dates (with --csv)")
    p.add_argument("--dividend", type=float, default=0.53)
    args = p.parse_args(argv)

    if args.csv:
        scenarios = [load_csv_scenario(args.csv, _dates(args.earnings), _dates(args.ex_div), args.dividend)]
    else:
        scenarios = builtin_scenarios()
        if args.scenario != "all":
            scenarios = [s for s in scenarios if s.name == args.scenario]
            if not scenarios:
                names = ", ".join(s.name for s in builtin_scenarios())
                p.error(f"unknown scenario; choose from: {names}")

    fills = ["mid", "cap"] if args.fill == "both" else [args.fill]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = [run_replay(s, fill_mode=f) for s in scenarios for f in fills]
    for r in results:
        _write_events(r, out)
    summary = _summary_md(results)
    (out / "summary.md").write_text(summary)
    print(summary)
    return 1 if any(r.violations for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
