"""Strategy parameters.

Every number in the rulebook lives here, so a rule change is a config change,
not a code change. Broker and Telegram credentials are added in step 3.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TrancheConfig(BaseModel):
    name: str
    contracts: int = 3
    writable: bool = True
    dte_min: int = 0
    dte_max: int = 0
    delta_min: float = 0.0
    delta_max: float = 0.0

    @property
    def delta_target(self) -> float:
        return round((self.delta_min + self.delta_max) / 2, 4)


def _default_tranches() -> list[TrancheConfig]:
    return [
        TrancheConfig(name="A", dte_min=28, dte_max=35, delta_min=0.14, delta_max=0.16),
        TrancheConfig(name="B", dte_min=40, dte_max=49, delta_min=0.10, delta_max=0.13),
        TrancheConfig(name="C", contracts=0, writable=False),
    ]


class StrategyConfig(BaseModel):
    symbol: str = "META"
    total_shares: int = 900
    # Shares that must never be covered by a call (Tranche C).
    core_shares: int = 300
    tranches: list[TrancheConfig] = Field(default_factory=_default_tranches)

    # Hard cap on short calls across the whole account (A + B). Guarantees C stays clean.
    max_total_short_contracts: int = 6

    # --- Opening new contracts ---
    # Expiry must land at least this many calendar days before the next earnings date.
    new_open_earnings_blackout_days: int = 14
    # After earnings, wait this many full trading sessions before opening anything.
    post_earnings_wait_sessions: int = 2
    # Ignore strikes whose bid is below this (no point selling $0.02 calls).
    min_open_bid: float = 0.10

    # --- Earnings window ---
    # At or inside this many trading days to earnings, close everything.
    earnings_close_window_tdays: int = 5

    # --- Ex-dividend guard ---
    ex_div_guard_tdays: int = 3
    ex_div_time_value_buffer: float = 0.15

    # --- Normal-day triggers ---
    proximity_pct: float = 0.98          # spot >= strike * 0.98 -> defensive roll
    profit_target_pct: float = 0.50      # mid <= 50% of entry credit -> close
    time_stop_dte: int = 21
    time_stop_close_profit_pct: float = 0.40

    # --- Roll target search ---
    roll_dte_min: int = 30
    roll_dte_max: int = 45
    short_roll_min_dte: int = 14
    short_roll_earnings_buffer_tdays: int = 5
    # Minimum net credit for a roll, measured at the ladder caps (worst-case fill). 0 = flat.
    roll_min_net_credit: float = 0.0
    # Policy knobs for research (defaults = the agreed rulebook).
    proximity_roll_enabled: bool = True      # False: proximity always closes
    defensive_roll_max_delta: float = 1.0    # e.g. 0.30: refuse defensive rolls above this delta
    time_stop_fallback: str = "close"        # "close" | "hold": what 21 DTE does when no credit roll exists

    # --- Order ladder ---
    ladder_step: float = 0.05
    ladder_step_seconds: int = 30
    ladder_cap_spread_fraction: float = 0.60

    # --- Execution safety (used from step 3 onward) ---
    kill_switch: bool = False

    @model_validator(mode="after")
    def _check(self) -> "StrategyConfig":
        names = [t.name for t in self.tranches]
        if len(set(names)) != len(names):
            raise ValueError("tranche names must be unique")
        writable = sum(t.contracts for t in self.tranches if t.writable)
        if writable > self.max_total_short_contracts:
            raise ValueError("writable tranches exceed max_total_short_contracts")
        if writable * 100 > self.total_shares - self.core_shares:
            raise ValueError("writable contracts would encumber the core shares")
        for t in self.tranches:
            if not t.writable and t.contracts != 0:
                raise ValueError(f"non-writable tranche {t.name} must have 0 contracts")
        if self.time_stop_fallback not in ("close", "hold"):
            raise ValueError("time_stop_fallback must be 'close' or 'hold'")
        if not 0.5 <= self.ladder_cap_spread_fraction < 1.0:
            raise ValueError("ladder cap must be between mid (0.5) and natural (1.0)")
        return self

    def tranche(self, name: str) -> TrancheConfig:
        for t in self.tranches:
            if t.name == name:
                return t
        raise KeyError(name)
