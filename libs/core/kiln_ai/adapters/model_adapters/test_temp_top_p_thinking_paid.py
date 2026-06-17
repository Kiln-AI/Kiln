"""Paid tests for the temperature / top_p / thinking-level interaction on
Anthropic models.

Anthropic has two sampling restrictions that collide with thinking levels:

1. ``temp_top_p_exclusive``: you may only set a custom value for ONE of
   ``temperature`` or ``top_p`` (not both). Kiln already guards this with a
   clear ``ValueError`` in ``build_completion_kwargs``.

2. When extended thinking is enabled (Kiln sends ``reasoning_effort``),
   Anthropic requires ``temperature`` to be 1 (and disallows custom ``top_p``).
   Kiln does NOT guard this today, so a user who sets a custom temperature on a
   thinking-enabled Anthropic model gets an opaque provider 400 that
   ``format_error_message`` collapses to "An unexpected error occurred." The
   native-Anthropic thinking dropdown also has no "None" entry, so there is no
   way to turn thinking off and use a custom temperature instead.

These tests pin the *intended* behavior:

- A custom temperature/top_p combined with thinking should fail fast with a
  clear, actionable Kiln ``ValueError`` (NOT an opaque provider error, and NOT
  by silently dropping the user's value).
- Setting ``thinking_level="none"`` should disable thinking and let a custom
  temperature / top_p through (this is the "try None" escape hatch we want to
  verify actually works against the live provider).

Run with: ``--runpaid``.
"""

from pathlib import Path

import pytest

import kiln_ai.datamodel as datamodel
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.ml_model_list import (
    ModelName,
    ModelProviderName,
    built_in_models,
)
from kiln_ai.adapters.model_adapters.test_paid_utils import (
    skip_if_missing_provider_keys,
)
from kiln_ai.adapters.model_adapters.test_thinking_level_paid import (
    reasoning_content_from_run,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

# A short prompt that reliably elicits internal reasoning on thinking models
# while staying cheap.
PROMPT = (
    "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the "
    "ball. How much does the ball cost? Answer with just the dollar amount."
)

# Expected outcomes for each interaction case.
EXPECT_REASONING = "reasoning"  # call succeeds and returns reasoning content
EXPECT_NO_REASONING = "no_reasoning"  # call succeeds with no reasoning content
EXPECT_KILN_VALUE_ERROR = "kiln_value_error"  # fail fast with a clear ValueError


# Native-Anthropic models that expose thinking levels but are currently broken
# for reasons UNRELATED to the temperature/top_p vs thinking bug, so we exclude
# them from this regression suite and track them separately:
#   - Opus 4.6/4.7/4.8: extended thinking 400s because litellm emits the legacy
#     thinking.type="enabled" block, but these models require Anthropic's newer
#     "adaptive" thinking API (thinking.type="adaptive" + output_config.effort).
#   - Opus 4.7/4.8 additionally reject `temperature`/`top_p` as deprecated, even
#     with thinking disabled.
# These look like a litellm-version / model-config gap, not this bug. Including
# them would keep the suite permanently red on issues this test isn't about.
KNOWN_BROKEN_THINKING_MODELS = {
    ModelName.claude_opus_4_6,
    ModelName.claude_opus_4_7,
    ModelName.claude_opus_4_8,
}


def native_anthropic_thinking_models() -> list[str]:
    """Native-Anthropic models that exhibit *only* the temperature/top_p vs
    thinking bug this suite guards against.

    Selects providers that expose thinking levels including both "none" (off)
    and "high" (the on-level we exercise) -- these share Sonnet 4.6's
    preconditions (``temp_top_p_exclusive`` + reasoning-effort thinking).
    Derived dynamically so new Anthropic models are covered automatically, minus
    the ``KNOWN_BROKEN_THINKING_MODELS`` that fail for unrelated reasons.
    """
    names: list[str] = []
    for model in built_in_models:
        if model.name in KNOWN_BROKEN_THINKING_MODELS:
            continue
        for provider in model.providers:
            if provider.name != ModelProviderName.anthropic:
                continue
            levels = set((provider.available_thinking_levels or {}).values())
            if {"none", "high"} <= levels:
                names.append(model.name)
                break
    return names


# Resolve once at import so a config drift that empties the list fails loudly at
# collection time instead of silently turning this regression suite into a no-op.
NATIVE_ANTHROPIC_THINKING_MODELS = native_anthropic_thinking_models()
assert NATIVE_ANTHROPIC_THINKING_MODELS, (
    "Expected at least one native Anthropic model exposing thinking levels "
    "{'none', 'high'}; model config may have drifted."
)


def build_test_task(tmp_path: Path) -> datamodel.Task:
    project = datamodel.Project(name="test", path=tmp_path / "test.kiln")
    project.save_to_file()
    task = datamodel.Task(
        parent=project,
        name="test task",
        instruction="You are a careful assistant.",
    )
    task.save_to_file()
    return task


# (case_id, thinking_level, temperature, top_p, expected_outcome)
INTERACTION_CASES = [
    # Baseline: thinking on with default sampling works (defaults of 1.0 are
    # dropped before the call, so Anthropic is happy).
    pytest.param(
        "high", 1.0, 1.0, EXPECT_REASONING, id="thinking_high__default_sampling"
    ),
    # THE BUG: thinking on + a custom temperature. Anthropic requires temp==1
    # when thinking is enabled. We want a clear Kiln error, not a 400.
    pytest.param(
        "high", 0.5, 1.0, EXPECT_KILN_VALUE_ERROR, id="thinking_high__custom_temp"
    ),
    # thinking on + a custom top_p. Anthropic also disallows custom top_p with
    # thinking enabled.
    pytest.param(
        "high", 1.0, 0.8, EXPECT_KILN_VALUE_ERROR, id="thinking_high__custom_top_p"
    ),
    # The "try None" escape hatch: disabling thinking should let a custom
    # temperature through and produce no reasoning content.
    pytest.param(
        "none", 0.5, 1.0, EXPECT_NO_REASONING, id="thinking_none__custom_temp"
    ),
    # Disabling thinking should also let a custom top_p through.
    pytest.param(
        "none", 1.0, 0.8, EXPECT_NO_REASONING, id="thinking_none__custom_top_p"
    ),
    # Existing guard: temp AND top_p both custom is rejected with a clear
    # ValueError regardless of thinking. Locks in current behavior.
    pytest.param("high", 0.5, 0.8, EXPECT_KILN_VALUE_ERROR, id="custom_temp_and_top_p"),
]


@pytest.mark.paid
@pytest.mark.parametrize("model_name", NATIVE_ANTHROPIC_THINKING_MODELS)
@pytest.mark.parametrize(
    ("thinking_level", "temperature", "top_p", "expected"),
    INTERACTION_CASES,
)
async def test_anthropic_temp_top_p_thinking_interaction(
    tmp_path,
    model_name: str,
    thinking_level: str,
    temperature: float,
    top_p: float,
    expected: str,
):
    provider_name = ModelProviderName.anthropic
    skip_if_missing_provider_keys(provider_name)

    task = build_test_task(tmp_path)
    adapter = adapter_for_task(
        task,
        KilnAgentRunConfigProperties(
            model_name=model_name,
            model_provider_name=provider_name,
            prompt_id="simple_prompt_builder",
            structured_output_mode="default",
            thinking_level=thinking_level,
            temperature=temperature,
            top_p=top_p,
        ),
    )

    if expected == EXPECT_KILN_VALUE_ERROR:
        with pytest.raises(KilnRunError) as exc_info:
            await adapter.invoke(PROMPT)
        err = exc_info.value
        # The failure must be a clear, pre-call Kiln ValueError, not an opaque
        # provider error (which format_error_message turns into the useless
        # "An unexpected error occurred.").
        assert isinstance(err.original, ValueError), (
            f"Expected a clear Kiln ValueError for thinking_level={thinking_level!r}, "
            f"temperature={temperature}, top_p={top_p}, but got "
            f"{err.error_type}: {err.original}"
        )
        message = str(err.original).lower()
        assert any(term in message for term in ("temperature", "top_p", "thinking")), (
            f"Error message should mention the conflicting params, got: {err.original}"
        )
        return

    run = await adapter.invoke(PROMPT)
    reasoning_content = reasoning_content_from_run(run)

    if expected == EXPECT_NO_REASONING:
        assert reasoning_content is None, (
            f"Expected no reasoning for thinking_level={thinking_level!r}, "
            f"but got {len(reasoning_content or '')} chars"
        )
    else:  # EXPECT_REASONING
        assert reasoning_content is not None, (
            f"Expected reasoning for thinking_level={thinking_level!r}, but got None"
        )
