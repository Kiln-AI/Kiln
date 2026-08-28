"""Golden-protocol harness: checked-in fixtures == new engine.

See ``golden_scenarios.py`` for the scenario definitions and the fixture
lifecycle. The fixtures were pinned from the (since deleted) old loops, so
``test_engine_matches_fixture`` is the durable contract: the unified engine
must produce the identical upstream request-body sequence for the same
scenario/policy, forever.

Bodies are compared as parsed JSON (the fake client parses each POST), so
dict key order is irrelevant — exactly the equivalence the backend sees.
"""

from __future__ import annotations

import pytest

from .golden_scenarios import SCENARIOS, GoldenScenario, fixture_path, load_fixture

_IDS = [s.name for s in SCENARIOS]


def test_every_scenario_has_a_checked_in_fixture():
    # A missing fixture means someone added a scenario without regenerating:
    #   uv run python -m app.desktop.studio_server.chat.runtime.golden_scenarios
    for scenario in SCENARIOS:
        assert fixture_path(scenario.name).exists(), (
            f"missing golden fixture for {scenario.name!r}; regenerate via "
            "`uv run python -m app.desktop.studio_server.chat.runtime.golden_scenarios`"
        )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
async def test_engine_matches_fixture(scenario: GoldenScenario):
    bodies = await scenario.run_engine()
    assert bodies == load_fixture(scenario.name), (
        f"the unified engine's upstream protocol for {scenario.name!r} "
        "diverged from the golden contract pinned from the old loops"
    )
