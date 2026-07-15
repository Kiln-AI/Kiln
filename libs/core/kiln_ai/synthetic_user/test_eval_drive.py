"""Unit tests for drive_case_for_eval.

`adapter_for_task` and `SyntheticUserDriver` are monkeypatched — no model
calls. The tests pin the persisted-drive contract (KIL-761): every turn
saves via the adapter with parent_task_run chaining, the adapter stamps
run_config_id, and conversation continuity rides prior_trace.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.datamodel.eval import SyntheticUserInfo
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.synthetic_user import eval_drive as eval_drive_mod
from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.synthetic_user.eval_drive import drive_case_for_eval
from kiln_ai.synthetic_user.models import SyntheticUserDriverConfig

_INFO = SyntheticUserInfo(
    persona="frustrated customer",
    goal="get a refund",
    behavior_guidance="be polite then escalate",
)

_SU_CONFIG = SyntheticUserDriverConfig(
    model_name="claude_4_5_haiku",
    model_provider_name=ModelProviderName.openrouter,
)


def _target_run_config() -> KilnAgentRunConfigProperties:
    return KilnAgentRunConfigProperties(
        model_name="gpt_5_5",
        model_provider_name=ModelProviderName.openrouter,
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.default,
        tools_config=ToolsRunConfig(tools=[]),
    )


def _fake_saved_run(trace: list[dict], run_id: str) -> Mock:
    """What adapter.invoke returns with allow_saving on: a persisted TaskRun
    carrying the cumulative trace."""
    run = Mock(spec=TaskRun)
    run.id = run_id
    run.trace = trace
    return run


class _FakeAdapter:
    """Records invoke calls; each returns a run whose trace grew by one
    user/assistant round-trip, like the real adapter."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.returned: list[Mock] = []

    async def invoke(
        self, *, input, input_source=None, prior_trace=None, parent_task_run=None
    ):
        self.calls.append(
            {
                "input": input,
                "input_source": input_source,
                "prior_trace": prior_trace,
                "parent_task_run": parent_task_run,
            }
        )
        new_trace = [
            *(prior_trace or []),
            {"role": "user", "content": input},
            {"role": "assistant", "content": f"reply-{len(self.calls)}"},
        ]
        run = _fake_saved_run(new_trace, run_id=f"run_{len(self.calls)}")
        self.returned.append(run)
        return run


@pytest.fixture
def fake_adapter(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeAdapter, dict]:
    adapter = _FakeAdapter()
    captured: dict[str, Any] = {}

    def _factory(task, run_config, base_adapter_config=None):
        captured["task"] = task
        captured["run_config"] = run_config
        captured["adapter_config"] = base_adapter_config
        return adapter

    monkeypatch.setattr(eval_drive_mod, "adapter_for_task", _factory)
    return adapter, captured


@pytest.fixture
def fake_su_driver(monkeypatch: pytest.MonkeyPatch) -> Mock:
    instance = Mock(spec=SyntheticUserDriver)
    instance.respond = AsyncMock(
        side_effect=[(f"follow-up-{i}", 0.0) for i in range(1, 10)]
    )
    captured_ctor: dict[str, Any] = {}

    def _ctor(info, config):
        captured_ctor["info"] = info
        captured_ctor["config"] = config
        return instance

    monkeypatch.setattr(eval_drive_mod, "SyntheticUserDriver", _ctor)
    instance.ctor_args = captured_ctor
    return instance


@pytest.mark.asyncio
async def test_drives_turns_and_returns_leaf(fake_adapter, fake_su_driver) -> None:
    adapter, _ = fake_adapter
    task = Mock(spec=Task)

    leaf = await drive_case_for_eval(
        seed_prompt="opening message",
        synthetic_user_info=_INFO,
        target_task=task,
        target_run_config=_target_run_config(),
        su_driver_config=_SU_CONFIG,
        turns=3,
        skills={},
    )

    assert len(adapter.calls) == 3
    # Turn 1 opens with the seed; later turns carry the SU's follow-ups.
    assert adapter.calls[0]["input"] == "opening message"
    assert adapter.calls[1]["input"] == "follow-up-1"
    assert adapter.calls[2]["input"] == "follow-up-2"
    # Continuity rides prior_trace, growing turn over turn.
    assert adapter.calls[0]["prior_trace"] is None
    assert len(adapter.calls[2]["prior_trace"]) == 4
    # Persisted runs chain: each turn's parent is the previous turn's run.
    assert adapter.calls[0]["parent_task_run"] is None
    assert adapter.calls[1]["parent_task_run"] is adapter.returned[0]
    assert adapter.calls[2]["parent_task_run"] is adapter.returned[1]
    # The leaf is the last turn's run: persisted, full cumulative trace.
    assert leaf is adapter.returned[2]
    assert leaf.id is not None
    assert len(leaf.trace) == 6

    # The SU driver was built from the typed persona.
    assert fake_su_driver.ctor_args["info"] is _INFO
    assert fake_su_driver.ctor_args["config"] is _SU_CONFIG


@pytest.mark.asyncio
async def test_adapter_configured_to_persist(fake_adapter, fake_su_driver) -> None:
    """The target adapter saves every driven turn (KIL-761), stamps the run
    config id for the runner's reuse scan, and gets the caller's preloaded
    skills."""
    _, captured = fake_adapter
    task = Mock(spec=Task)
    skills = {"skill_tool": Mock()}

    await drive_case_for_eval(
        seed_prompt="hi",
        synthetic_user_info=_INFO,
        target_task=task,
        target_run_config=_target_run_config(),
        su_driver_config=_SU_CONFIG,
        turns=1,
        skills=skills,
        task_run_config_id="rc_123",
    )

    assert captured["task"] is task
    assert captured["adapter_config"].allow_saving is True
    assert captured["adapter_config"].task_run_config_id == "rc_123"
    assert captured["adapter_config"].skills is skills


@pytest.mark.asyncio
async def test_input_source_attributes_su_driver(fake_adapter, fake_su_driver) -> None:
    adapter, _ = fake_adapter

    await drive_case_for_eval(
        seed_prompt="hi",
        synthetic_user_info=_INFO,
        target_task=Mock(spec=Task),
        target_run_config=_target_run_config(),
        su_driver_config=_SU_CONFIG,
        turns=1,
        skills={},
    )

    source = adapter.calls[0]["input_source"]
    assert source.properties["model_name"] == "claude_4_5_haiku"
    assert source.properties["model_provider"] == "openrouter"
    assert source.properties["adapter_name"] == "kiln_synthetic_user_eval_driver"
