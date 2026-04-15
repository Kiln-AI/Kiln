"""Tests that LiteLlmAdapter preserves the partial trace when the underlying
LLM call fails. Exercises the interaction between the caller-owned `messages`
list (allocated in BaseAdapter) and the in-place mutation contract in
`LiteLlmAdapter._run()`.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import litellm
import pytest

from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.adapters.model_adapters.litellm_config import LiteLlmConfig
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties


@pytest.fixture
def simple_task(tmp_path):
    project_path = tmp_path / "p" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="P", path=str(project_path))
    project.save_to_file()

    task = Task(
        name="T",
        instruction="Do a thing.",
        parent=project,
    )
    task.save_to_file()
    return task


@pytest.fixture
def config():
    return LiteLlmConfig(
        base_url=None,
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4o-mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
        default_headers=None,
        additional_body_options={"api_key": "test_key"},
    )


def _make_rate_limit_error():
    try:
        return litellm.RateLimitError(
            message="upstream rate limit",
            model="gpt-4o-mini",
            llm_provider="openai",
        )
    except TypeError:
        return litellm.RateLimitError("upstream rate limit")  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_litellm_adapter_wraps_error_with_partial_trace(simple_task, config):
    """When acompletion throws, the resulting KilnRunError carries the initial
    system + user messages built by the chat formatter."""
    adapter = LiteLlmAdapter(config=config, kiln_task=simple_task)

    mock_config_obj = Mock()
    mock_config_obj.open_ai_api_key = "mock_api_key"
    mock_config_obj.user_id = "test_user"
    mock_config_obj.autosave_runs = False

    rate_limit = _make_rate_limit_error()

    with (
        patch.object(
            LiteLlmAdapter,
            "acompletion_checking_response",
            new=AsyncMock(side_effect=rate_limit),
        ),
        patch("kiln_ai.utils.config.Config.shared", return_value=mock_config_obj),
    ):
        with pytest.raises(KilnRunError) as ei:
            await adapter.invoke("hello world")

    err = ei.value
    assert err.error_type == "RateLimitError"
    assert str(err) == "Rate limit exceeded. Wait a moment and try again."
    assert err.original is rate_limit

    # The chat formatter produces at least a system message + the user input;
    # verify both survived the exception boundary.
    assert err.partial_trace is not None
    assert len(err.partial_trace) >= 2
    roles = [m["role"] for m in err.partial_trace]
    assert "system" in roles
    assert "user" in roles
    # And the user message contains our input.
    user_messages = [m for m in err.partial_trace if m["role"] == "user"]
    assert any("hello world" in json.dumps(m.get("content")) for m in user_messages)


@pytest.mark.asyncio
async def test_litellm_adapter_passes_through_kiln_run_error(simple_task, config):
    """If _run raises an already-wrapped KilnRunError, it's not re-wrapped."""
    adapter = LiteLlmAdapter(config=config, kiln_task=simple_task)

    inner = RuntimeError("inner")
    pre_wrapped = KilnRunError(
        message="pre-wrapped",
        partial_trace=[{"role": "user", "content": "u"}],
        original=inner,
    )

    mock_config_obj = Mock()
    mock_config_obj.open_ai_api_key = "mock_api_key"
    mock_config_obj.user_id = "test_user"
    mock_config_obj.autosave_runs = False

    async def raise_pre_wrapped(self, input, messages, prior_trace=None):
        raise pre_wrapped

    with (
        patch.object(LiteLlmAdapter, "_run", new=raise_pre_wrapped),
        patch("kiln_ai.utils.config.Config.shared", return_value=mock_config_obj),
    ):
        with pytest.raises(KilnRunError) as ei:
            await adapter.invoke("hello")

    assert ei.value is pre_wrapped
