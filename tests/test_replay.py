"""Every built-in scenario must finish with zero rule violations under both fill assumptions."""

from __future__ import annotations

import pytest

from meta_covered_calls.replay.runner import run_replay
from meta_covered_calls.replay.scenarios import builtin_scenarios


@pytest.mark.parametrize("scenario", builtin_scenarios(), ids=lambda s: s.name)
@pytest.mark.parametrize("fill", ["mid", "cap"])
def test_scenario_has_no_violations(scenario, fill):
    result = run_replay(scenario, fill_mode=fill)
    assert result.violations == []
    assert result.encumbered_days["C"] == 0
    assert any(e.action == "OPEN" for e in result.events)
