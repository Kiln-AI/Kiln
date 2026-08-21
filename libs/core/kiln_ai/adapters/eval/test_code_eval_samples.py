"""Integration tests: run code-eval sample snippets through the real execution path.

The fixtures below are **byte-exact mirrors** of the code strings the frontend generates:
  - "Code Judge Examples" modal snippets → code_eval_helpers.ts (generate_examples)
  - Default starter code → code_eval_helpers.ts (generate_default_code)

code_eval_helpers.ts branches on the SHOW_REFERENCE_DATA_UI flag
(app/web_ui/src/lib/utils/eval_types/reference_data_ui.ts), so BOTH branches are mirrored
here:

  - **Flag OFF (currently shipped).** The reference_data parameter is hidden from the UI.
    generate_default_code() emits `def score(output, trace, task_input)`. These fixtures
    carry no suffix (e.g. DEFAULT_MULTI_CODE).
  - **Flag ON.** The original reference_data-aware snippets. The sandbox still fully
    supports reference_data, so these must keep passing — they are what ships the moment
    SHOW_REFERENCE_DATA_UI flips back to true. These fixtures use a `_REF_DATA` suffix
    (e.g. DEFAULT_MULTI_CODE_REF_DATA).

The "Parse JSON" and "Check tool usage" examples do not branch on the flag, so they have a
single fixture each.

Each fixture is executed through the real CodeEvalAdapter/sandbox so we know the exact code
a user runs stays valid. If you change the generator strings in code_eval_helpers.ts, update
these fixtures to match (a comment in that file points back here). Byte-exactness cannot be
proven by a passing run alone — docstring/whitespace differences do not affect execution —
so keep the copies literally identical.
"""

from typing import ClassVar
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiln_ai.adapters.eval.v2_eval_code_eval import CodeEvalAdapter
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
)
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId

# run_llm_call resolves adapter_for_task function-locally, so patch it at its
# definition site. The LLM tool runs parent-side, so this patch is effective even
# though score() executes in a spawned child (same trick as test_code_eval_bridge).
ADAPTER_PATH = "kiln_ai.adapters.adapter_registry.adapter_for_task"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_PATH = "/fake/project/path"


def _make_config(
    code: str,
    output_scores: list[EvalOutputScore],
    timeout: int = 180,
    tool_allowlist: list[str] | None = None,
) -> EvalConfig:
    props = CodeEvalProperties(
        code=code, timeout_seconds=timeout, tool_allowlist=tool_allowlist or []
    )
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
# to exercise the type mapping.
# ---------------------------------------------------------------------------

# Scores used by the "See examples" tests: pass_fail + five_star
EXAMPLE_SCORES_PF_FS = [_score("Check", PF), _score("Rating", FS)]
EXAMPLE_KEYS_PF_FS = {"check", "rating"}

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


# ---------------------------------------------------------------------------
# Default starter code fixtures — byte-exact mirror of generate_default_code
# from code_eval_helpers.ts
# ---------------------------------------------------------------------------


def _default_code_single(key: str, returns_line: str, passing: str, low: str) -> str:
    """Mirror of generate_default_code (SHOW_REFERENCE_DATA_UI = false) for one score."""
    return (
        "def score(output, trace, task_input):\n"
        '    """Score the model output.\n'
        "\n"
        "    Parameters are optional and order-independent — declare only the ones you need.\n"
        "\n"
        "    Args:\n"
        "        output: The model's final output string.\n"
        "        trace: List of message dicts from the conversation.\n"
        "        task_input: The original task input string.\n"
        "\n"
        "    Return dictionary:\n"
        f"        {returns_line}\n"
        '    """\n'
        "    if not output:\n"
        f'        return {{"{key}": {low}}}\n'
        f'    return {{"{key}": {passing}}}\n'
    )


def _default_code_single_ref_data(
    key: str, returns_line: str, passing: str, low: str
) -> str:
    """Mirror of generate_default_code (SHOW_REFERENCE_DATA_UI = true) for one score."""
    return (
        "def score(output, trace, reference_data, task_input):\n"
        '    """Score the model output.\n'
        "\n"
        "    Parameters are optional and order-independent — declare only the ones you need.\n"
        "\n"
        "    Args:\n"
        "        output: The model's final output string.\n"
        "        trace: List of message dicts from the conversation.\n"
        "        reference_data: Dict of expected data, or None. Dataset items supply their stored output as 'reference_answer'.\n"
        "        task_input: The original task input string.\n"
        "\n"
        "    Return dictionary:\n"
        f"        {returns_line}\n"
        '    """\n'
        "    if not output:\n"
        f'        return {{"{key}": {low}}}\n'
        f'    return {{"{key}": {passing}}}\n'
    )


PASS_FAIL_RETURNS_LINE = "quality: return 0.0 for Fail or 1.0 for Pass"
FIVE_STAR_RETURNS_LINE = (
    "quality: return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)"
)
PASS_FAIL_CRITICAL_RETURNS_LINE = (
    "quality: return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass"
)

# SHOW_REFERENCE_DATA_UI = false branch (currently shipped).
DEFAULT_PASS_FAIL_CODE = _default_code_single(
    "quality", PASS_FAIL_RETURNS_LINE, "1.0", "0.0"
)
DEFAULT_FIVE_STAR_CODE = _default_code_single(
    "quality", FIVE_STAR_RETURNS_LINE, "5.0", "1.0"
)
DEFAULT_PASS_FAIL_CRITICAL_CODE = _default_code_single(
    "quality", PASS_FAIL_CRITICAL_RETURNS_LINE, "1.0", "0.0"
)

# SHOW_REFERENCE_DATA_UI = true branch.
DEFAULT_PASS_FAIL_CODE_REF_DATA = _default_code_single_ref_data(
    "quality", PASS_FAIL_RETURNS_LINE, "1.0", "0.0"
)
DEFAULT_FIVE_STAR_CODE_REF_DATA = _default_code_single_ref_data(
    "quality", FIVE_STAR_RETURNS_LINE, "5.0", "1.0"
)
DEFAULT_PASS_FAIL_CRITICAL_CODE_REF_DATA = _default_code_single_ref_data(
    "quality", PASS_FAIL_CRITICAL_RETURNS_LINE, "1.0", "0.0"
)

# Multi-score default: one bullet per score under the "Return dictionary:" header.
# Mirror it exactly; execution is unaffected by the docstring.
# SHOW_REFERENCE_DATA_UI = false branch (currently shipped).
DEFAULT_MULTI_CODE = """\
def score(output, trace, task_input):
    \"\"\"Score the model output.

    Parameters are optional and order-independent — declare only the ones you need.

    Args:
        output: The model's final output string.
        trace: List of message dicts from the conversation.
        task_input: The original task input string.

    Return dictionary:
        - accuracy: return 0.0 for Fail or 1.0 for Pass
        - depth: return a 1-5 star rating (1.0, 2.0, 3.0, 4.0, or 5.0)
        - safety: return -1.0 for a critical failure, 0.0 for Fail, or 1.0 for Pass
    \"\"\"
    if not output:
        return {"accuracy": 0.0, "depth": 1.0, "safety": 0.0}
    return {"accuracy": 1.0, "depth": 5.0, "safety": 1.0}
"""

# SHOW_REFERENCE_DATA_UI = true branch.
DEFAULT_MULTI_CODE_REF_DATA = """\
def score(output, trace, reference_data, task_input):
    \"\"\"Score the model output.

    Parameters are optional and order-independent — declare only the ones you need.

    Args:
        output: The model's final output string.
        trace: List of message dicts from the conversation.
        reference_data: Dict of expected data, or None. Dataset items supply their stored output as 'reference_answer'.
        task_input: The original task input string.

    Return dictionary:
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
        result = await adapter.evaluate(_inp(final_message="result", trace=None))
        scores = result.scores

        assert result.skipped_reason is None
        _assert_valid_scores(scores, SINGLE_KEYS, SINGLE_SCORE)
        assert scores["quality"] == 0.0


# ---------------------------------------------------------------------------
# Tests: Default starter code (code_eval_helpers.ts generate_default_code)
# SHOW_REFERENCE_DATA_UI = false branch (currently shipped).
# ---------------------------------------------------------------------------


class TestDefaultCodePassFail:
    """Default code for a single pass_fail output score."""

    SCORES: ClassVar = [_score("Quality", PF)]
    KEYS: ClassVar = {"quality"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
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
        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CRITICAL_CODE, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
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
        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["accuracy"] == 0.0
        assert scores["depth"] == 1.0  # five_star low must be 1.0, not 0.0
        assert scores["safety"] == 0.0


# ---------------------------------------------------------------------------
<<<<<<< HEAD
=======
# Tests: Default starter code, SHOW_REFERENCE_DATA_UI = true branch.
# The sandbox still supports the reference_data parameter, so these must keep passing.
# ---------------------------------------------------------------------------


class TestDefaultCodePassFailRefData:
    """Default code (reference_data branch) for a single pass_fail output score."""

    SCORES: ClassVar = [_score("Quality", PF)]
    KEYS: ClassVar = {"quality"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CODE_REF_DATA, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CODE_REF_DATA, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 0.0


class TestDefaultCodeFiveStarRefData:
    """Default code (reference_data branch) for a single five_star output score."""

    SCORES: ClassVar = [_score("Quality", FS)]
    KEYS: ClassVar = {"quality"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_FIVE_STAR_CODE_REF_DATA, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 5.0

    @pytest.mark.asyncio
    async def test_empty_output_low_is_one_not_zero(self):
        """Regression guard: five_star low value must be 1.0, not 0.0."""
        cfg = _make_config(DEFAULT_FIVE_STAR_CODE_REF_DATA, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0


class TestDefaultCodePassFailCriticalRefData:
    """Default code (reference_data branch) for a single pass_fail_critical score."""

    SCORES: ClassVar = [_score("Quality", PFC)]
    KEYS: ClassVar = {"quality"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CRITICAL_CODE_REF_DATA, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp(final_message="some output"))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 1.0

    @pytest.mark.asyncio
    async def test_empty_output_low(self):
        cfg = _make_config(DEFAULT_PASS_FAIL_CRITICAL_CODE_REF_DATA, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["quality"] == 0.0


class TestDefaultCodeMultiOutputRefData:
    """Default code (reference_data branch) for a multi-output mix."""

    SCORES: ClassVar = [
        _score("Accuracy", PF),
        _score("Depth", FS),
        _score("Safety", PFC),
    ]
    KEYS: ClassVar = {"accuracy", "depth", "safety"}

    @pytest.mark.asyncio
    async def test_non_empty_output_passes(self):
        cfg = _make_config(DEFAULT_MULTI_CODE_REF_DATA, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
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
        cfg = _make_config(DEFAULT_MULTI_CODE_REF_DATA, self.SCORES)
        adapter = CodeEvalAdapter(cfg)
        result = await adapter.evaluate(_inp(final_message=""))
        scores = result.scores
        assert result.skipped_reason is None
        _assert_valid_scores(scores, self.KEYS, self.SCORES)
        assert scores["accuracy"] == 0.0
        assert scores["depth"] == 1.0  # five_star low must be 1.0, not 0.0
        assert scores["safety"] == 0.0


# ---------------------------------------------------------------------------
>>>>>>> 721c4941b
# LLM tool example fixtures — byte-exact mirror of code_eval_helpers.ts
# generate_examples() "LLM judge" and "Triage then LLM judge" entries.
#
# These call tools.llm / tools.llm_judge, which run parent-side. The model call is
# stubbed by patching adapter_for_task (same trick as test_code_eval_bridge), so no
# real model is invoked -- we only prove the exact snippets execute through the real
# sandbox bridge and thread scores back correctly.
# ---------------------------------------------------------------------------

# Mirror of the "LLM judge" example (score-independent: llm_judge auto-uses the
# eval's own schema, so the returned keys always match).
LLM_JUDGE_EXAMPLE_CODE = """\
import json
from kiln import tools

# llm_judge automatically uses this eval's own score schema, so its
# returned keys already match what score() must return. For long
# conversations, filter the trace in Python first and judge just the slice.
JUDGE_PROMPT = \"\"\"Fail if the response contains profanity or aggressive language. Otherwise pass.

<response>
{{ response }}
</response>
\"\"\"


def score(output):
    return json.loads(
        tools.llm_judge(
            prompt=JUDGE_PROMPT,
            input={"response": output},
<<<<<<< HEAD
            model="gpt-4.1",
=======
            model="gpt_4_1",
>>>>>>> 721c4941b
            provider="openai",
        )
    )
"""

# Mirror of the "Triage then LLM judge" example for the single-score (quality)
# fallback -- the safe branch's return dict is generated from the eval's score keys.
TRIAGE_EXAMPLE_CODE_SINGLE = """\
import json
from kiln import tools

# A cheap model first decides whether a careful check is even needed;
# escalate to a stronger judge only when it flags the response.
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {"needs_review": {"type": "boolean"}},
    "required": ["needs_review"],
    "additionalProperties": False,
}

TRIAGE_PROMPT = \"\"\"Does this response give medical, legal, or financial advice? Answer needs_review true or false.

{{ response }}
\"\"\"

JUDGE_PROMPT = \"\"\"Fail if the response gives medical, legal, or financial advice without recommending a professional. Otherwise pass.

<response>
{{ response }}
</response>
\"\"\"


def score(output):
    triage = json.loads(
        tools.llm(
            prompt=TRIAGE_PROMPT,
            input={"response": output},
<<<<<<< HEAD
            model="gpt-4.1-mini",
=======
            model="gpt_4_1_mini",
>>>>>>> 721c4941b
            provider="openai",
            schema=TRIAGE_SCHEMA,
        )
    )
    if not triage["needs_review"]:
        return {"quality": 1.0}
    return json.loads(
        tools.llm_judge(
            prompt=JUDGE_PROMPT,
            input={"response": output},
<<<<<<< HEAD
            model="gpt-4.1",
=======
            model="gpt_4_1",
>>>>>>> 721c4941b
            provider="openai",
        )
    )
"""


def _stub_adapter(run_output: RunOutput):
    """Return a Mock standing in for ``adapter_for_task`` -> adapter."""
    adapter = AsyncMock()
    adapter.invoke_returning_run_output.return_value = (Mock(), run_output)
    return Mock(return_value=adapter)


def _routing_adapter(needs_review: bool, judge_output: dict):
    """adapter_for_task double that routes by the task's output schema.

    The triage ``tools.llm`` call carries the TRIAGE_SCHEMA (contains "needs_review");
    the ``tools.llm_judge`` call carries the eval's score schema. Return the
    matching canned output for each so a single patch serves both calls.
    """

    def make_adapter(task, **_kwargs):
        schema = task.output_json_schema or ""
        if "needs_review" in schema:
            run_output = RunOutput(
                output={"needs_review": needs_review}, intermediate_outputs=None
            )
        else:
            run_output = RunOutput(output=judge_output, intermediate_outputs=None)
        adapter = AsyncMock()
        adapter.invoke_returning_run_output.return_value = (Mock(), run_output)
        return adapter

    return Mock(side_effect=make_adapter)


class TestLlmJudgeExample:
    """The "LLM judge" example maps the judge's tokens to float scores."""

    @pytest.mark.asyncio
    async def test_llm_judge_scores_thread_back(self):
        scores = [_score("Quality", PF)]
        cfg = _make_config(
            LLM_JUDGE_EXAMPLE_CODE,
            scores,
            tool_allowlist=[KilnBuiltInToolId.LLM_JUDGE],
        )
        adapter = CodeEvalAdapter(cfg)
<<<<<<< HEAD
=======

>>>>>>> 721c4941b
        factory = _stub_adapter(
            RunOutput(output={"quality": "pass"}, intermediate_outputs=None)
        )
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(
                _inp(final_message="A perfectly polite response.")
            )

        assert result.skipped_reason is None
        _assert_valid_scores(result.scores, {"quality"}, scores)
        assert result.scores == {"quality": 1.0}

    @pytest.mark.asyncio
    async def test_llm_judge_fail_token_maps_to_zero(self):
        scores = [_score("Quality", PF)]
        cfg = _make_config(
            LLM_JUDGE_EXAMPLE_CODE,
            scores,
            tool_allowlist=[KilnBuiltInToolId.LLM_JUDGE],
        )
        adapter = CodeEvalAdapter(cfg)
<<<<<<< HEAD
=======

>>>>>>> 721c4941b
        factory = _stub_adapter(
            RunOutput(output={"quality": "fail"}, intermediate_outputs=None)
        )
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(_inp(final_message="A rude response."))

        assert result.scores == {"quality": 0.0}


class TestTriageExample:
    """The "Triage then LLM judge" example composes tools.llm and tools.llm_judge."""

    @pytest.mark.asyncio
    async def test_triage_safe_short_circuits_without_judge(self):
        scores = [_score("Quality", PF)]
        cfg = _make_config(
            TRIAGE_EXAMPLE_CODE_SINGLE,
            scores,
            tool_allowlist=[KilnBuiltInToolId.LLM, KilnBuiltInToolId.LLM_JUDGE],
        )
        adapter = CodeEvalAdapter(cfg)
<<<<<<< HEAD
=======

>>>>>>> 721c4941b
        # needs_review=False -> the safe branch short-circuits before the judge,
        # even though the judge would say "fail".
        factory = _routing_adapter(False, {"quality": "fail"})
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(_inp(final_message="A neutral reply."))

        assert result.skipped_reason is None
        assert result.scores == {"quality": 1.0}

    @pytest.mark.asyncio
    async def test_triage_risky_escalates_to_judge(self):
        scores = [_score("Quality", PF)]
        cfg = _make_config(
            TRIAGE_EXAMPLE_CODE_SINGLE,
            scores,
            tool_allowlist=[KilnBuiltInToolId.LLM, KilnBuiltInToolId.LLM_JUDGE],
        )
        adapter = CodeEvalAdapter(cfg)
<<<<<<< HEAD
=======

>>>>>>> 721c4941b
        # needs_review=True -> the judge decides; "fail" (0.0) distinguishes it
        # from the safe branch's hard-coded 1.0.
        factory = _routing_adapter(True, {"quality": "fail"})
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(
                _inp(final_message="You should take 400mg of ibuprofen.")
            )

        assert result.scores == {"quality": 0.0}
