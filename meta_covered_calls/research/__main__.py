"""Research runs: regimes, delta sweep, Monte Carlo, stylized long history.

    python -m meta_covered_calls.research regimes            # 4 regimes x 4 delta settings + earnings audit
    python -m meta_covered_calls.research montecarlo --paths 200
    python -m meta_covered_calls.research history
    python -m meta_covered_calls.research all

Reports go to reports/research/. Exit code 1 if any run breaks a rule.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..config import StrategyConfig, TrancheConfig
from ..replay.runner import ReplayResult, run_replay
from .regimes import earnings_moved_up, random_path, regime_scenarios, stylized_history

# --------------------------------------------------------------------------- strategy variants


def delta_variant(target: float, width: float = 0.015) -> StrategyConfig:
    """Both tranches aim at the same delta; DTE bands and every other rule unchanged."""
    base = StrategyConfig()
    tranches = []
    for t in base.tranches:
        if t.writable:
            t = TrancheConfig(**{**t.model_dump(), "delta_min": round(target - width, 3),
                                 "delta_max": round(target + width, 3)})
        tranches.append(t)
    return base.model_copy(update={"tranches": tranches})


VARIANTS: dict[str, StrategyConfig] = {
    "current (A .15 / B .115)": StrategyConfig(),
    "delta 0.10": delta_variant(0.10),
    "delta 0.15": delta_variant(0.15),
    "delta 0.20": delta_variant(0.20),
}
POLICIES: dict[str, StrategyConfig] = {
    "proximity: always close": StrategyConfig(proximity_roll_enabled=False),
    "defensive roll cap 0.30Δ": StrategyConfig(defensive_roll_max_delta=0.30),
    "21 DTE: hold if no roll": StrategyConfig(time_stop_fallback="hold"),
    "cap 0.30Δ + hold": StrategyConfig(defensive_roll_max_delta=0.30, time_stop_fallback="hold"),
}
ALL = {**VARIANTS, **POLICIES}


def _run(args) -> tuple[str, ReplayResult]:
    variant, scenario = args
    return variant, run_replay(scenario, cfg=ALL[variant], fill_mode="cap")


def _parallel(jobs: list) -> list[tuple[str, ReplayResult]]:
    with ProcessPoolExecutor() as pool:
        return list(pool.map(_run, jobs, chunksize=1))


def _money(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


# --------------------------------------------------------------------------- regimes + sweep

def regimes_report(out: Path) -> bool:
    scenarios = regime_scenarios()
    results = _parallel([(v, s) for s in scenarios for v in VARIANTS])
    lines = [
        "# Regime tests and delta sweep",
        "",
        "Fills assumed at the ladder cap (worst case). Yield = annualized premium ÷ average value of the "
        "600 writable shares. Defensive = proximity or ex-div rule fired.",
        "",
        "| Regime | Delta | Spot | Gross premium | Net premium | Net yield | Defensive rolls | "
        "Defensive closes | A / B written | Max shorts | Violations |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for v, r in results:
        days = sorted(r.scenario.closes)
        s0, s1 = r.scenario.closes[days[0]], r.scenario.closes[days[-1]]
        lines.append(
            f"| {r.scenario.name} | {v} | {s0:.0f}→{s1:.0f} | {_money(r.gross_premium)} | "
            f"{_money(r.net_premium)} | {r.net_yield:+.1%} | {r.defensive_rolls} | {r.defensive_closes} | "
            f"{r.written_pct('A'):.0%} / {r.written_pct('B'):.0%} | {r.max_shorts} | {len(r.violations)} |"
        )

    lines += ["", "## Earnings audit (current settings)", "",
              "Short calls open at any close inside the 5 trading days before each print must be 0.", "",
              "| Regime | Print | Engine believed (10 days prior) | Max shorts in 5-day window | "
              "Closed by earnings rule | Next-day gap |",
              "|---|---|---|---:|---:|---:|"]
    for v, r in results:
        if not v.startswith("current"):
            continue
        for a in r.earnings_audit:
            moved = " (moved)" if a.engine_saw and a.engine_saw != a.earnings else ""
            lines.append(f"| {r.scenario.name} | {a.earnings} | {a.engine_saw}{moved} | "
                         f"{a.max_shorts_in_window} | {a.closed_by_rule} | {a.gap_pct:+.1%} |")

    # The moved-earnings stress over many random paths: does the 5-day backstop ever have to act?
    stress = _parallel([(v, earnings_moved_up(seed=1000 + i)) for i in range(40) for v in ALL])
    lines += ["", "## Moved-earnings stress: 40 random paths per setting", "",
              "Each print lands 3 weeks before the estimate the engine was using, and the real date is "
              "announced only 10 days ahead, so contracts opened or rolled under the estimate can be "
              "open into the real print. The 5-day close rule is the backstop.", "",
              "| Setting | Moved prints | Prints where the 5-day rule had to act | Positions it closed | "
              "Short calls open inside the 5-day window | Violations |",
              "|---|---:|---:|---:|---:|---:|"]
    stress_by: dict[str, list[ReplayResult]] = defaultdict(list)
    for v, r in stress:
        stress_by[v].append(r)
    for v, rs in stress_by.items():
        audits = [a for r in rs for a in r.earnings_audit if a.engine_saw and a.engine_saw != a.earnings]
        fired = sum(a.closed_by_rule for a in audits)
        lines.append(f"| {v} | {len(audits)} | {sum(1 for a in audits if a.closed_by_rule)} | {fired} | "
                     f"{sum(a.max_shorts_in_window for a in audits)} | {sum(len(r.violations) for r in rs)} |")
    results = results + stress

    bad = [(v, r) for v, r in results if r.violations]
    lines += ["", "## Violations", ""]
    lines += ["None in any regime or delta setting."] if not bad else [
        f"- {r.scenario.name} / {v}: {x}" for v, r in bad for x in r.violations]
    _write(out / "regimes.md", lines)
    return not bad and all(a.max_shorts_in_window == 0 for _, r in results for a in r.earnings_audit)


# --------------------------------------------------------------------------- Monte Carlo

def _pct(values: list[float], q: float) -> float:
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def montecarlo_report(out: Path, paths: int) -> bool:
    scenarios = [random_path(seed) for seed in range(1, paths + 1)]
    results = _parallel([(v, s) for s in scenarios for v in ALL])
    by_variant: dict[str, list[ReplayResult]] = defaultdict(list)
    for v, r in results:
        by_variant[v].append(r)

    stock = [r.scenario.closes[max(r.scenario.closes)] / r.scenario.closes[min(r.scenario.closes)] - 1
             for r in by_variant["current (A .15 / B .115)"]]
    lines = [
        f"# Monte Carlo: {paths} random one-year paths per setting",
        "",
        "Each path draws its own drift (mean +12%, sd 30%), vol (25-50%), earnings gaps (sd 9%), "
        "~2 news jumps, and an implied/realized vol ratio of 1.0-1.2x. Same paths for every setting. "
        "Fills at the ladder cap.",
        "",
        f"Stock return across paths: median {statistics.median(stock):+.0%}, "
        f"10th pct {_pct(stock, 0.10):+.0%}, 90th pct {_pct(stock, 0.90):+.0%}.",
        "",
        "| Setting | Median net yield | 10th pct (bad year) | 90th pct (good year) | Paths with net gain | "
        "Avg gross premium | Avg defensive rolls | Avg written A / B | Max shorts (any day, any path) | "
        "Paths with violations |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for v, rs in by_variant.items():
        y = [r.net_yield for r in rs]
        lines.append(
            f"| {v} | {statistics.median(y):+.2%} | {_pct(y, 0.10):+.2%} | {_pct(y, 0.90):+.2%} | "
            f"{sum(1 for r in rs if r.net_premium > 0) / len(rs):.0%} | "
            f"{_money(statistics.mean(r.gross_premium for r in rs))} | "
            f"{statistics.mean(r.defensive_rolls for r in rs):.1f} | "
            f"{statistics.mean(r.written_pct('A') for r in rs):.0%} / "
            f"{statistics.mean(r.written_pct('B') for r in rs):.0%} | "
            f"{max(r.max_shorts for r in rs)} | {sum(1 for r in rs if r.violations)} |"
        )

    lines += ["", "## Median net yield by stock outcome", "",
              "| Stock year | Paths | " + " | ".join(ALL) + " |",
              "|---|---:|" + "---:|" * len(ALL)]
    buckets = [("down > 20%", -9, -0.20), ("down 0-20%", -0.20, 0.0), ("up 0-20%", 0.0, 0.20),
               ("up 20-50%", 0.20, 0.50), ("up > 50%", 0.50, 99)]
    for label, lo, hi in buckets:
        idx = [i for i, s in enumerate(stock) if lo <= s < hi]
        if not idx:
            continue
        cells = [f"{statistics.median(by_variant[v][i].net_yield for i in idx):+.2%}" for v in ALL]
        lines.append(f"| {label} | {len(idx)} | " + " | ".join(cells) + " |")

    any_bad = any(r.violations for _, r in results)
    lines += ["", "## Violations", "", "None across all paths and settings." if not any_bad else
              "\n".join(f"- {r.scenario.name} / {v}: {r.violations[0]}" for v, r in results if r.violations)]
    _write(out / "montecarlo.md", lines)
    return not any_bad


# --------------------------------------------------------------------------- stylized history

def history_report(out: Path) -> bool:
    scenario = stylized_history()
    results = _parallel([(v, scenario) for v in ALL])
    years = sorted({d.year for d in scenario.closes})
    lines = [
        "# Stylized 12-year history (2013-2024)",
        "",
        "A path shaped like META's history using approximate calendar-year returns and vols, "
        "**not real prices**. It is useful for seeing how the rules behave across a long run that includes "
        "big bull years and two deep drawdowns (2018, 2022). Fills at the ladder cap.",
        "",
        "| Setting | Gross premium | Net premium | Avg net yield / yr | Defensive rolls | Defensive closes | "
        "A / B written | Max shorts | Violations |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for v, r in results:
        lines.append(f"| {v} | {_money(r.gross_premium)} | {_money(r.net_premium)} | {r.net_yield:+.2%} | "
                     f"{r.defensive_rolls} | {r.defensive_closes} | {r.written_pct('A'):.0%} / "
                     f"{r.written_pct('B'):.0%} | {r.max_shorts} | {len(r.violations)} |")

    lines += ["", "## Realized premium by year (cash in minus buybacks, as % of writable shares' value)", "",
              "| Year | Stock | " + " | ".join(ALL) + " |", "|---|---:|" + "---:|" * len(ALL)]
    for y in years:
        days = [d for d in scenario.closes if d.year == y]
        px = sum(scenario.closes[d] for d in days) / len(days) * 600
        stock = scenario.closes[max(days)] / scenario.closes[min(days)] - 1
        cells = [f"{sum(e.cash for e in r.events if e.day.year == y) / px:+.2%}" for _, r in results]
        lines.append(f"| {y} | {stock:+.0%} | " + " | ".join(cells) + " |")

    bad = [(v, r) for v, r in results if r.violations]
    lines += ["", "## Violations", "", "None." if not bad else
              "\n".join(f"- {v}: {x}" for v, r in bad for x in r.violations[:5])]
    _write(out / "history.md", lines)
    return not bad


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m meta_covered_calls.research")
    p.add_argument("what", choices=["regimes", "montecarlo", "history", "all"])
    p.add_argument("--paths", type=int, default=200)
    p.add_argument("--out", default="reports/research")
    args = p.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ok = True
    if args.what in ("regimes", "all"):
        ok &= regimes_report(out)
    if args.what in ("montecarlo", "all"):
        ok &= montecarlo_report(out, args.paths)
    if args.what in ("history", "all"):
        ok &= history_report(out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
