"""Integration tests: run code-eval sample snippets through the real execution path.

Sample code is mirrored verbatim from the frontend:
  - "See examples" snippets → code_eval_form.svelte
  - Default starter code shape → code_eval_helpers.ts (generate_default_code)
Keep these fixtures in sync with those sources.
"""

from typing import ClassVar
from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.v2_eval_code_eval import (
    CodeEvalAdapter,
    _trusted_projects,
    grant_code_eval_trust,
)
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
)

# ---------------------------------------------------------------------------
# Trust cleanup (prevent leakage between tests)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_trust():
    _trusted_projects.clear()
    yield
    _trusted_projects.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_PATH = "/fake/project/path"


def _make_config(
    code: str,
    output_scores: list[EvalOutputScore],
    timeout: int = 30,
) -> EvalConfig:
    props = CodeEvalProperties(code=code, timeout_seconds=timeout)
    parent_eval = Mock()
    parent_eval.output_scores = output_scores
    parent_task = Mock()
    parent_project = Mock()
    parent_project.id = "project-sample-tests"
    parent_project.path = PROJECT_PATH
    parent_task.parent = parent_project
    parent_eval.parent_task.return_value = parent_task

    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    cfg.parent_eval.return_value = parent_eval
    return cfg


def _inp(**overrides: object) -> EvalTaskInput:
    defaults: dict = {
        "final_message": "Hello world",
        "trace": None,
        "reference_data": None,
        "task_input": None,
    }
    defaults.update(overrides)
    return EvalTaskInput(**defaults)


def _score(name: str, typ: TaskOutputRatingType) -> EvalOutputScore:
    return EvalOutputScore(name=name, instruction=f"Score: {name}", type=typ)


PF = TaskOutputRatingType.pass_fail
FS = TaskOutputRatingType.five_star
PFC = TaskOutputRatingType.pass_fail_critical


# ---------------------------------------------------------------------------
# Sample code fixtures — verbatim from code_eval_form.svelte ("See examples")
# ---------------------------------------------------------------------------

# Mirror of code_eval_form.svelte "Parse JSON" example.
PARSE_JSON_CODE = """\
import json

def score(output, trace, reference_data, task_input, kiln):
    \"\"\"Check if the output is valid JSON with required fields.\"\"\"
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return {"valid_json": 0.0, "has_fields": 0.0}

    required = ["name", "description"]
    has_all = all(k in data for k in required)
    return {
        "valid_json": 1.0,
        "has_fields": kiln.pass_fail(has_all),
    }
"""

# Mirror of code_eval_form.svelte "Check tool usage" example.
CHECK_TOOL_USAGE_CODE = """\
def score(output, trace, reference_data, task_input, kiln):
    \"\"\"Verify the model used the expected tools.\"\"\"
    tool_calls = kiln.get_tool_calls(trace)
    used_search = kiln.has_tool_call(tool_calls, "search")
    call_count = kiln.count_tool_calls(tool_calls, "search")

    return {
        "used_search": kiln.pass_fail(used_search),
        "search_count": kiln.five_star(max(min(call_count, 5), 1)),
    }
"""

# Mirror of code_eval_form.svelte "Domain-specific grading" example.
DOMAIN_GRADING_CODE = """\
def score(output, trace, reference_data, task_input, kiln):
    \"\"\"Grade output against domain-specific criteria.\"\"\"
    expected = (reference_data or {}).get("expected_answer", "")

    contains = kiln.assert_contains(output, expected) if expected else True

    word_count = len(output.split())
    concise = 10 <= word_count <= 200

    return {
        "contains_answer": kiln.pass_fail(contains),
        "conciseness": kiln.pass_fail(concise),
        "length_score": kiln.five_star(
            5 if word_count < 50 else 3 if word_count < 150 else 1
        ),
    }
"""


# ---------------------------------------------------------------------------
# Default starter code fixtures — matching generate_default_code output shape
# from code_eval_helpers.ts
# ---------------------------------------------------------------------------


def _default_code_single(key: str, passing: str, low: str) -> str:
    """Build a minimal default-code snippet for a single output score."""
    return (
        "def score(output, trace, reference_data, task_input, kiln):\n"
        '    """Score the model output."""\n'
        "    if not output:\n"
        f'        return {{"{key}": {low}}}\n'
        f'    return {{"{key}": {passing}}}\n'
    )


DEFAULT_PASS_FAIL_CODE = _default_code_single("quality", "1.0", "0.0")
DEFAULT_FIVE_STAR_CODE = _default_code_single("quality", "5.0", "1.0")
DEFAULT_PASS_FAIL_CRITICAL_CODE = _default_code_single("quality", "1.0", "0.0")

DEFAULT_MULTI_CODE = (
    "def score(output, trace, reference_data, task_input, kiln):\n"
    '    """Score the model output."""\n'
    "    if not output:\n"
    '        return {"accuracy": 0.0, "depth": 1.0, "safety": 0.0}\n'
    '    return {"accuracy": 1.0, "depth": 5.0, "safety": 1.0}\n'
)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _assert_valid_scores(
    scores: dict[str, float],
    expected_keys: set[str],
    output_scores: list[EvalOutputScore],
) -> None:
    """Assert returned keys match exactly and values are in valid ranges."""
    assert set(scores.keys()) == expected_keys
    score_types = {s.json_key(): s.type for s in output_scores}
    for key, val in scores.items():
        assert isinstance(val, float), f"{key} is not a float"
        typ = score_types[key]
        if typ == PF:
            assert 0.0 <= val <= 1.0, f"{key} pass_fail out of range: {val}"
        elif typ == FS:
            assert 1.0 <= val <= 5.0, f"{key} five_star out of range: {val}"
        elif typ == PFC:
            assert -1.0 <= val <= 1.0, f"{key} pass_fail_critical out of range: {val}"


# ---------------------------------------------------------------------------
# Tests: "See examples" snippets (code_eval_form.svelte)
# ---------------------------------------------------------------------------


class TestParseJsonExample:
    """Parse JSON example from code_eval_form.svelte."""

    SCORES: ClassVar = [_score("Valid JSON", PF), _score("Has Fields", PF)]
    KEYS: ClassVar = {"valid_json", "has_fields"}

    @pytest.mark.asyncio
    async def test_valid_json_with_required_fields(self):
        cfg = _make_config(PARSE_JSON_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message='{"name": "Alice", "description": "A person"}')
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["valid_json"] == 1.0
        assert scores["has_fields"] == 1.0

    @pytest.mark.asyncio
    async def test_valid_json_missing_fields(self):
        cfg = _make_config(PARSE_JSON_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message='{"name": "Alice"}')
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["valid_json"] == 1.0
        assert scores["has_fields"] == 0.0

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        cfg = _make_config(PARSE_JSON_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message="not json at all")
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["valid_json"] == 0.0
        assert scores["has_fields"] == 0.0


class TestCheckToolUsageExample:
    """Check tool usage example from code_eval_form.svelte."""

    SCORES: ClassVar = [_score("Used Search", PF), _score("Search Count", FS)]
    KEYS: ClassVar = {"used_search", "search_count"}

    @pytest.mark.asyncio
    async def test_trace_with_search_calls(self):
        cfg = _make_config(CHECK_TOOL_USAGE_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        trace = [
            {"role": "tool_call", "name": "search", "arguments": {"q": "test"}},
            {"role": "tool_call", "name": "search", "arguments": {"q": "more"}},
            {"role": "tool_call", "name": "other_tool", "arguments": {}},
        ]
        inp = _inp(final_message="result", trace=trace)
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["used_search"] == 1.0
        assert scores["search_count"] == 2.0

    @pytest.mark.asyncio
    async def test_zero_matching_tool_calls(self):
        """Regression: zero search calls must not raise -- five_star clamped to 1."""
        cfg = _make_config(CHECK_TOOL_USAGE_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        trace = [{"role": "tool_call", "name": "other_tool", "arguments": {}}]
        inp = _inp(final_message="result", trace=trace)
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["used_search"] == 0.0
        assert scores["search_count"] == 1.0  # max(min(0, 5), 1) == 1

    @pytest.mark.asyncio
    async def test_none_trace(self):
        """None trace should not raise -- get_tool_calls returns []."""
        cfg = _make_config(CHECK_TOOL_USAGE_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message="result", trace=None)
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["used_search"] == 0.0
        assert scores["search_count"] == 1.0

    @pytest.mark.asyncio
    async def test_many_search_calls_capped_at_five(self):
        cfg = _make_config(CHECK_TOOL_USAGE_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        trace = [
            {"role": "tool_call", "name": "search", "arguments": {"q": f"q{i}"}}
            for i in range(10)
        ]
        inp = _inp(final_message="result", trace=trace)
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["used_search"] == 1.0
        assert scores["search_count"] == 5.0  # max(min(10, 5), 1) == 5


class TestDomainGradingExample:
    """Domain-specific grading example from code_eval_form.svelte."""

    SCORES: ClassVar = [
        _score("Contains Answer", PF),
        _score("Conciseness", PF),
        _score("Length Score", FS),
    ]
    KEYS: ClassVar = {"contains_answer", "conciseness", "length_score"}

    @pytest.mark.asyncio
    async def test_output_contains_expected_answer(self):
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = "The answer is 42 and here is some additional context to pad it out a bit more words"
        inp = _inp(
            final_message=output,
            reference_data={"expected_answer": "42"},
        )
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["contains_answer"] == 1.0
        assert scores["conciseness"] == 1.0
        assert scores["length_score"] == 5.0

    @pytest.mark.asyncio
    async def test_output_missing_expected_answer(self):
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 20)
        inp = _inp(
            final_message=output,
            reference_data={"expected_answer": "UNICORN_NOT_PRESENT"},
        )
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["contains_answer"] == 0.0
        assert scores["conciseness"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_reference_data(self):
        """Empty/missing reference_data should not raise -- expected defaults to ''."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 30)
        inp = _inp(final_message=output, reference_data=None)
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["contains_answer"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_reference_data_dict(self):
        """reference_data={} (no expected_answer key) should not raise."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 30)
        inp = _inp(final_message=output, reference_data={})
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["contains_answer"] == 1.0

    @pytest.mark.asyncio
    async def test_very_short_output_not_concise(self):
        """Output with fewer than 10 words is not concise."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = "short"
        inp = _inp(final_message=output, reference_data=None)
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["conciseness"] == 0.0
        assert scores["length_score"] == 5.0

    @pytest.mark.asyncio
    async def test_long_output_length_score(self):
        """Output with 150+ words gets length_score of 1."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 160)
        inp = _inp(final_message=output, reference_data=None)
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["conciseness"] == 1.0
        assert scores["length_score"] == 1.0

    @pytest.mark.asyncio
    async def test_medium_output_length_score(self):
        """Output with 50-149 words gets length_score of 3."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 80)
        inp = _inp(final_message=output, reference_data=None)
        scores, reason, _ = await adapter.evaluate(inp)

        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["length_score"] == 3.0


# ---------------------------------------------------------------------------
# Tests: Default starter code (code_eval_helpers.ts generate_default_code)
# ---------------------------------------------------------------------------


class TestDefaultCodePassFail:
    """Default code for a single pass_fail output score."""

    SCORES: ClassVar = [_score("Quality", PF)]
    KEYS: ClassVar = {"quality"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        scores, reason, _ = await adapter.evaluate(_inp(final_message="some output"))
        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        scores, reason, _ = await adapter.evaluate(_inp(final_message=""))
        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 0.0


class TestDefaultCodeFiveStar:
    """Default code for a single five_star output score."""

    SCORES: ClassVar = [_score("Quality", FS)]
    KEYS: ClassVar = {"quality"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_FIVE_STAR_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        scores, reason, _ = await adapter.evaluate(_inp(final_message="some output"))
        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 5.0

    @pytest.mark.asyncio
    async def test_empty_output_low_is_one_not_zero(self):
        """Regression guard: five_star low value must be 1.0, not 0.0."""
        cfg = _make_config(DEFAULT_FIVE_STAR_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        scores, reason, _ = await adapter.evaluate(_inp(final_message=""))
        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0


class TestDefaultCodePassFailCritical:
    """Default code for a single pass_fail_critical output score."""

    SCORES: ClassVar = [_score("Quality", PFC)]
    KEYS: ClassVar = {"quality"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CRITICAL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        scores, reason, _ = await adapter.evaluate(_inp(final_message="some output"))
        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CRITICAL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        scores, reason, _ = await adapter.evaluate(_inp(final_message=""))
        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 0.0


class TestDefaultCodeMultiOutput:
    """Default code for multi-output mix (pass_fail + five_star + pass_fail_critical)."""

    SCORES: ClassVar = [
        _score("Accuracy", PF),
        _score("Depth", FS),
        _score("Safety", PFC),
    ]
    KEYS: ClassVar = {"accuracy", "depth", "safety"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_MULTI_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        scores, reason, _ = await adapter.evaluate(_inp(final_message="some output"))
        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["accuracy"] == 1.0
        assert scores["depth"] == 5.0
        assert scores["safety"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low_values(self):
        """Regression guard: five_star low is 1.0, pass_fail/pfc low is 0.0."""
        cfg = _make_config(DEFAULT_MULTI_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        scores, reason, _ = await adapter.evaluate(_inp(final_message=""))
        assert reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["accuracy"] == 0.0
        assert scores["depth"] == 1.0  # five_star low must be 1.0, not 0.0
        assert scores["safety"] == 0.0
