"""Tranche state: applying fills, and saving/loading it as JSON.

The local file only remembers which tranche owns which contract and what it
was sold for. From step 3 on, the broker's positions are the source of truth
and this file is reconciled against them on every run.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .config import StrategyConfig
from .models import Action, Decision, Instruction, PortfolioState, Position, TrancheState


@dataclass(frozen=True)
class Fill:
    """Per-share leg prices actually achieved. A close has no sell price; an open has no buy price."""

    buy_price: float | None = None
    sell_price: float | None = None


def new_state(cfg: StrategyConfig) -> PortfolioState:
    return PortfolioState(tranches={t.name: TrancheState(t.name) for t in cfg.tranches})


def apply_fill(state: PortfolioState, decision: Decision, fill: Fill, today: date) -> None:
    """Update the state after a ticket has filled."""
    if decision.ticket is None:
        return
    tstate = state.tranches[decision.tranche]
    held = tstate.position

    if decision.action is Action.CLOSE:
        tstate.position = None
        return

    sell = next(leg for leg in decision.ticket.legs if leg.instruction is Instruction.SELL_TO_OPEN)
    if fill.sell_price is None:
        raise ValueError("open/roll fill needs a sell price")

    if decision.action is Action.OPEN:
        tstate.position = Position(
            tranche=decision.tranche, expiry=sell.expiry, strike=sell.strike, contracts=sell.quantity,
            entry_credit=fill.sell_price, opened_on=today, cumulative_credit=fill.sell_price,
        )
    elif decision.action is Action.ROLL:
        if held is None or fill.buy_price is None:
            raise ValueError("roll fill needs a held position and a buy price")
        tstate.position = Position(
            tranche=decision.tranche, expiry=sell.expiry, strike=sell.strike, contracts=sell.quantity,
            entry_credit=fill.sell_price, opened_on=today,
            cumulative_credit=held.cumulative_credit - fill.buy_price + fill.sell_price,
            roll_count=held.roll_count + 1,
        )


# -- persistence -------------------------------------------------------------

def _to_json(state: PortfolioState) -> dict:
    out = {}
    for name, t in state.tranches.items():
        pos = asdict(t.position) if t.position else None
        if pos:
            pos["expiry"] = pos["expiry"].isoformat()
            pos["opened_on"] = pos["opened_on"].isoformat()
        out[name] = {"position": pos}
    return {"version": 1, "tranches": out}


def _from_json(data: dict) -> PortfolioState:
    tranches = {}
    for name, t in data["tranches"].items():
        p = t.get("position")
        pos = None
        if p:
            p = dict(p)
            p["expiry"] = date.fromisoformat(p["expiry"])
            p["opened_on"] = date.fromisoformat(p["opened_on"])
            pos = Position(**p)
        tranches[name] = TrancheState(name, pos)
    return PortfolioState(tranches=tranches)


def save_state(state: PortfolioState, path: str | Path) -> None:
    """Atomic write: a crash mid-save never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(_to_json(state), f, indent=2)
    os.replace(tmp, path)


def load_state(path: str | Path, cfg: StrategyConfig) -> PortfolioState:
    path = Path(path)
    if not path.exists():
        return new_state(cfg)
    state = _from_json(json.loads(path.read_text()))
    for t in cfg.tranches:
        state.tranches.setdefault(t.name, TrancheState(t.name))
    return state
