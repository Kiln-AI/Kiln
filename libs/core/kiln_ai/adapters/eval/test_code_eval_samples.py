"""Integration tests: run code-eval sample snippets through the real execution path.

The fixtures below are **byte-exact mirrors** of the code strings the frontend generates:
  - "Code Judge Examples" modal snippets → code_eval_helpers.ts (generate_examples)
  - Default starter code → code_eval_helpers.ts (generate_default_code)

Each fixture is executed through the real CodeEvalAdapter/sandbox so we know the exact code
a user runs stays valid. If you change the generator strings in code_eval_helpers.ts, update
these fixtures to match (a comment in that file points back here). Byte-exactness cannot be
proven by a passing run alone — docstring/whitespace differences do not affect execution —
so keep the copies literally identical.
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
# Sample code fixtures — mirror of code_eval_helpers.ts generate_examples()
# Each example uses a test eval with both pass_fail and five_star scores
# (plus pass_fail_critical in the domain example) to exercise the type mapping.
# ---------------------------------------------------------------------------

# Scores used by the "See examples" tests: pass_fail + five_star
EXAMPLE_SCORES_PF_FS = [_score("Check", PF), _score("Rating", FS)]
EXAMPLE_KEYS_PF_FS = {"check", "rating"}

# Scores with an additional pass_fail_critical
EXAMPLE_SCORES_PF_FS_PFC = [
    _score("Check", PF),
    _score("Rating", FS),
    _score("Safety", PFC),
]
EXAMPLE_KEYS_PF_FS_PFC = {"check", "rating", "safety"}

# Mirror of code_eval_helpers.ts "Parse JSON" example (multi-score).
PARSE_JSON_CODE = """\
import json
from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(output):
    \"\"\"Check if the output is valid JSON with required fields.\"\"\"
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return {"check": 0.0, "rating": 1.0}

    required = ["name", "description"]
    has_all = all(k in data for k in required)
    passed = isinstance(data, dict) and has_all
    return {  # Adjust each score's logic for your eval
        "check": KilnEvalHelpers.pass_fail(passed),
        "rating": KilnEvalHelpers.five_star(5 if passed else 1),
    }
"""

# Mirror of code_eval_helpers.ts "Check tool usage" example (multi-score).
CHECK_TOOL_USAGE_CODE = """\
from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(trace):
    \"\"\"Verify the model used the expected tools.\"\"\"
    tool_calls = KilnEvalHelpers.get_tool_calls(trace)
    used_search = KilnEvalHelpers.has_tool_call(tool_calls, "search")
    call_count = KilnEvalHelpers.count_tool_calls(tool_calls, "search")

    return {  # Adjust each score's logic for your eval
        "check": KilnEvalHelpers.pass_fail(used_search),
        "rating": KilnEvalHelpers.five_star(max(min(call_count, 5), 1)),
    }
"""

# Mirror of code_eval_helpers.ts "Domain-specific grading" example (3-score).
DOMAIN_GRADING_CODE = """\
from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(output, reference_data):
    \"\"\"Grade output against domain-specific criteria.\"\"\"
    expected = (reference_data or {}).get("expected_answer", "")

    contains = KilnEvalHelpers.assert_contains(output, expected) if expected else True

    word_count = len(output.split())

    return {  # Adjust each score's logic for your eval
        "check": KilnEvalHelpers.pass_fail(contains),
        "rating": KilnEvalHelpers.five_star(5 if word_count < 50 else 3 if word_count < 150 else 1),
        "safety": KilnEvalHelpers.pass_fail(contains),
    }
"""


# ---------------------------------------------------------------------------
# Single-score (quality fallback) example fixtures — byte-exact mirror of
# generate_examples() for a single pass_fail score. These exercise the
# inline-return path (no multi-line dict, no "Adjust each score's logic" comment)
# that the multi-score fixtures above do not.
# ---------------------------------------------------------------------------

PARSE_JSON_CODE_SINGLE = """\
import json
from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(output):
    \"\"\"Check if the output is valid JSON with required fields.\"\"\"
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return {"quality": 0.0}

    required = ["name", "description"]
    has_all = all(k in data for k in required)
    passed = isinstance(data, dict) and has_all
    return {"quality": KilnEvalHelpers.pass_fail(passed)}
"""

CHECK_TOOL_USAGE_CODE_SINGLE = """\
from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(trace):
    \"\"\"Verify the model used the expected tools.\"\"\"
    tool_calls = KilnEvalHelpers.get_tool_calls(trace)
    used_search = KilnEvalHelpers.has_tool_call(tool_calls, "search")
    call_count = KilnEvalHelpers.count_tool_calls(tool_calls, "search")

    return {"quality": KilnEvalHelpers.pass_fail(used_search)}
"""

DOMAIN_GRADING_CODE_SINGLE = """\
from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers

def score(output, reference_data):
    \"\"\"Grade output against domain-specific criteria.\"\"\"
    expected = (reference_data or {}).get("expected_answer", "")

    contains = KilnEvalHelpers.assert_contains(output, expected) if expected else True

    word_count = len(output.split())

    return {"quality": KilnEvalHelpers.pass_fail(contains)}
"""


# ---------------------------------------------------------------------------
# Default starter code fixtures — byte-exact mirror of generate_default_code
# from code_eval_helpers.ts
# ---------------------------------------------------------------------------


def _default_code_single(key: str, returns_line: str, passing: str, low: str) -> str:
    """Byte-exact mirror of generate_default_code for a single output score."""
    return (
        "def score(output, trace, reference_data, task_input):\n"
        '    """Score the model output.\n'
        "\n"
        "    Parameters are optional and order-independent — declare only the ones you need.\n"
        "\n"
        "    Args:\n"
        "        output: The model's final output string.\n"
        "        trace: List of message dicts from the conversation.\n"
        "        reference_data: Dict of reference/expected data (if any).\n"
        "        task_input: The original task input string.\n"
        "\n"
        "    Returns:\n"
        f"        {returns_line}\n"
        '    """\n'
        "    if not output:\n"
        f'        return {{"{key}": {low}}}\n'
        f'    return {{"{key}": {passing}}}\n'
    )


DEFAULT_PASS_FAIL_CODE = _default_code_single(
    "quality", "quality: return 0.0 for Fail or 1.0 for Pass", "1.0", "0.0"
)
DEFAULT_FIVE_STAR_CODE = _default_code_single(
    "quality",
    "quality: return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)",
    "5.0",
    "1.0",
)
DEFAULT_PASS_FAIL_CRITICAL_CODE = _default_code_single(
    "quality",
    "quality: return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass",
    "1.0",
    "0.0",
)

# Multi-score default. NOTE: the generator indents the bullet lines 6 spaces -- less than
# the 8-space "A dictionary..." line above them (a cosmetic quirk in generate_default_code).
# Mirror it exactly; execution is unaffected by the docstring.
DEFAULT_MULTI_CODE = """\
def score(output, trace, reference_data, task_input):
    \"\"\"Score the model output.

    Parameters are optional and order-independent — declare only the ones you need.

    Args:
        output: The model's final output string.
        trace: List of message dicts from the conversation.
        reference_data: Dict of reference/expected data (if any).
        task_input: The original task input string.

    Returns:
        A dictionary of score names to scores:
      - accuracy: return 0.0 for Fail or 1.0 for Pass
      - depth: return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)
      - safety: return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass
    \"\"\"
    if not output:
        return {"accuracy": 0.0, "depth": 1.0, "safety": 0.0}
    return {"accuracy": 1.0, "depth": 5.0, "safety": 1.0}
"""


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
    """Parse JSON example from code_eval_helpers.ts generate_examples."""

    SCORES: ClassVar = EXAMPLE_SCORES_PF_FS
    KEYS: ClassVar = EXAMPLE_KEYS_PF_FS

    @pytest.mark.asyncio
    async def test_valid_json_with_required_fields(self):
        cfg = _make_config(PARSE_JSON_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message='{"name": "Alice", "description": "A person"}')
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 1.0
        assert scores["rating"] == 5.0

    @pytest.mark.asyncio
    async def test_valid_json_missing_fields(self):
        cfg = _make_config(PARSE_JSON_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message='{"name": "Alice"}')
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 0.0
        assert scores["rating"] == 1.0

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        cfg = _make_config(PARSE_JSON_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message="not json at all")
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 0.0
        assert scores["rating"] == 1.0

    @pytest.mark.asyncio
    async def test_json_array_not_dict(self):
        """A valid JSON array is not a dict -- passed should be False."""
        cfg = _make_config(PARSE_JSON_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message="[1, 2, 3]")
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 0.0
        assert scores["rating"] == 1.0


class TestCheckToolUsageExample:
    """Check tool usage example from code_eval_helpers.ts generate_examples."""

    SCORES: ClassVar = EXAMPLE_SCORES_PF_FS
    KEYS: ClassVar = EXAMPLE_KEYS_PF_FS

    @pytest.mark.asyncio
    async def test_trace_with_search_calls(self):
        cfg = _make_config(CHECK_TOOL_USAGE_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        trace = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "test"}'},
                    },
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "more"}'},
                    },
                    {
                        "id": "c3",
                        "type": "function",
                        "function": {"name": "other_tool", "arguments": "{}"},
                    },
                ],
            }
        ]
        inp = _inp(final_message="result", trace=trace)
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 1.0
        assert scores["rating"] == 2.0

    @pytest.mark.asyncio
    async def test_zero_matching_tool_calls(self):
        """Regression: zero search calls must not raise -- five_star clamped to 1."""
        cfg = _make_config(CHECK_TOOL_USAGE_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        trace = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "other_tool", "arguments": "{}"},
                    },
                ],
            }
        ]
        inp = _inp(final_message="result", trace=trace)
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 0.0
        assert scores["rating"] == 1.0  # max(min(0, 5), 1) == 1

    @pytest.mark.asyncio
    async def test_none_trace(self):
        """None trace should not raise -- get_tool_calls returns []."""
        cfg = _make_config(CHECK_TOOL_USAGE_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message="result", trace=None)
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 0.0
        assert scores["rating"] == 1.0

    @pytest.mark.asyncio
    async def test_many_search_calls_capped_at_five(self):
        cfg = _make_config(CHECK_TOOL_USAGE_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        trace = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"c{i}",
                        "type": "function",
                        "function": {"name": "search", "arguments": f'{{"q": "q{i}"}}'},
                    }
                    for i in range(10)
                ],
            }
        ]
        inp = _inp(final_message="result", trace=trace)
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 1.0
        assert scores["rating"] == 5.0  # max(min(10, 5), 1) == 5


class TestDomainGradingExample:
    """Domain-specific grading example from code_eval_helpers.ts generate_examples."""

    SCORES: ClassVar = EXAMPLE_SCORES_PF_FS_PFC
    KEYS: ClassVar = EXAMPLE_KEYS_PF_FS_PFC

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
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 1.0
        assert scores["safety"] == 1.0
        assert scores["rating"] == 5.0

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
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 0.0
        assert scores["safety"] == 0.0

    @pytest.mark.asyncio
    async def test_empty_reference_data(self):
        """Empty/missing reference_data should not raise -- expected defaults to ''."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 30)
        inp = _inp(final_message=output, reference_data=None)
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 1.0
        assert scores["safety"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_reference_data_dict(self):
        """reference_data={} (no expected_answer key) should not raise."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 30)
        inp = _inp(final_message=output, reference_data={})
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["check"] == 1.0
        assert scores["safety"] == 1.0

    @pytest.mark.asyncio
    async def test_short_output_high_rating(self):
        """Output with fewer than 50 words gets rating of 5."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = "short"
        inp = _inp(final_message=output, reference_data=None)
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["rating"] == 5.0

    @pytest.mark.asyncio
    async def test_long_output_low_rating(self):
        """Output with 150+ words gets rating of 1."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 160)
        inp = _inp(final_message=output, reference_data=None)
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["rating"] == 1.0

    @pytest.mark.asyncio
    async def test_medium_output_mid_rating(self):
        """Output with 50-149 words gets rating of 3."""
        cfg = _make_config(DOMAIN_GRADING_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        output = " ".join(["word"] * 80)
        inp = _inp(final_message=output, reference_data=None)
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["rating"] == 3.0


# ---------------------------------------------------------------------------
# Tests: single-score (quality fallback) example variants — inline-return path
# ---------------------------------------------------------------------------

SINGLE_SCORE: list[EvalOutputScore] = [_score("Quality", PF)]
SINGLE_KEYS = {"quality"}


class TestParseJsonExampleSingleScore:
    """Single-score variant of the Parse JSON example (inline return)."""

    @pytest.mark.asyncio
    async def test_valid_json_with_required_fields(self):
        cfg = _make_config(PARSE_JSON_CODE_SINGLE, SINGLE_SCORE)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message='{"name": "Alice", "description": "A person"}')
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, SINGLE_KEYS, SINGLE_SCORE)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        cfg = _make_config(PARSE_JSON_CODE_SINGLE, SINGLE_SCORE)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(final_message="not json at all")
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, SINGLE_KEYS, SINGLE_SCORE)
        assert scores["quality"] == 0.0


class TestCheckToolUsageExampleSingleScore:
    """Single-score variant of the Check tool usage example (inline return)."""

    @pytest.mark.asyncio
    async def test_search_tool_used(self):
        cfg = _make_config(CHECK_TOOL_USAGE_CODE_SINGLE, SINGLE_SCORE)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        trace = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "x"}'},
                    },
                ],
            }
        ]
        result = await adapter.evaluate(_inp(final_message="result", trace=trace))
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, SINGLE_KEYS, SINGLE_SCORE)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_no_tool_calls(self):
        cfg = _make_config(CHECK_TOOL_USAGE_CODE_SINGLE, SINGLE_SCORE)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        result = await adapter.evaluate(_inp(final_message="result", trace=None))
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, SINGLE_KEYS, SINGLE_SCORE)
        assert scores["quality"] == 0.0


class TestDomainGradingExampleSingleScore:
    """Single-score variant of the Domain-specific grading example (inline return)."""

    @pytest.mark.asyncio
    async def test_output_contains_expected(self):
        cfg = _make_config(DOMAIN_GRADING_CODE_SINGLE, SINGLE_SCORE)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(
            final_message="The answer is 42",
            reference_data={"expected_answer": "42"},
        )
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, SINGLE_KEYS, SINGLE_SCORE)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_output_missing_expected(self):
        cfg = _make_config(DOMAIN_GRADING_CODE_SINGLE, SINGLE_SCORE)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        inp = _inp(
            final_message="nothing relevant here",
            reference_data={"expected_answer": "UNICORN_NOT_PRESENT"},
        )
        result = await adapter.evaluate(inp)
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, SINGLE_KEYS, SINGLE_SCORE)
        assert scores["quality"] == 0.0


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

        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
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

        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 5.0

    @pytest.mark.asyncio
    async def test_empty_output_low_is_one_not_zero(self):
        """Regression guard: five_star low value must be 1.0, not 0.0."""
        cfg = _make_config(DEFAULT_FIVE_STAR_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
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

        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CRITICAL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
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

        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
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

        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["accuracy"] == 0.0
        assert scores["depth"] == 1.0  # five_star low must be 1.0, not 0.0
        assert scores["safety"] == 0.0
