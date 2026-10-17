"""Test support for trace toolset v1: the golden-file update option, the fixture
traces, and a seeded synthetic coding-agent trace generator."""

import json
from pathlib import Path
from typing import Any

import pytest

from kiln_ai.adapters.eval.trace_tools.v1.view import TraceView, build_view

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE_GOLDENS_OPTION = "--update-trace-tool-goldens"

# About 1,300 messages and 470k chars: large enough that whole-trace reads refuse.
GOLDEN_SYNTHETIC_ROUNDS = 520
GOLDEN_SYNTHETIC_TOOL_OUTPUT_CHARS = 600


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        UPDATE_GOLDENS_OPTION,
        action="store_true",
        default=False,
        help="Rewrite the trace toolset v1 golden files from the current output.",
    )


@pytest.fixture
def update_goldens(request: pytest.FixtureRequest) -> bool:
    # The option only exists when this conftest is loaded at startup, i.e. when
    # pytest is pointed at this directory or a file in it.
    return bool(request.config.getoption(UPDATE_GOLDENS_OPTION, default=False))


def golden_trace(name: str) -> list[Any]:
    if name == "synthetic":
        return synthetic_coding_trace(
            rounds=GOLDEN_SYNTHETIC_ROUNDS,
            tool_output_chars=GOLDEN_SYNTHETIC_TOOL_OUTPUT_CHARS,
        )
    path = GOLDEN_DIR / "traces" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def coding_trace() -> list[Any]:
    return golden_trace("coding_agent")


@pytest.fixture
def coding_view(coding_trace: list[Any]) -> TraceView:
    return build_view(coding_trace)


@pytest.fixture
def edge_trace() -> list[Any]:
    return golden_trace("edge_cases")


@pytest.fixture
def edge_view(edge_trace: list[Any]) -> TraceView:
    return build_view(edge_trace)


class _Lcg:
    """A fixed pseudo-random sequence. Unlike ``random``, its output is the same
    on every Python version, so the golden files built from it never drift."""

    def __init__(self, seed: int):
        self._state = seed

    def below(self, bound: int) -> int:
        self._state = (self._state * 6364136223846793005 + 1442695040888963407) % (
            1 << 64
        )
        return (self._state >> 33) % bound


_TOOL_WEIGHTS = (
    ("read_file", 8),
    ("grep", 3),
    ("edit_file", 2),
    ("run_tests", 1),
    ("list_dir", 1),
    ("web_fetch", 1),
)


def _pick_tool(rng: _Lcg) -> str:
    pick = rng.below(sum(weight for _, weight in _TOOL_WEIGHTS))
    for name, weight in _TOOL_WEIGHTS:
        if pick < weight:
            return name
        pick -= weight
    raise AssertionError("unreachable")


def _corpus() -> str:
    return "".join(
        f"{i:05d}    value_{i % 97} = compute(item_{i % 31}, limit={i % 13})  # step {i % 7}\n"
        for i in range(2_000)
    )


def synthetic_coding_trace(
    *, rounds: int, tool_output_chars: int, seed: int = 1
) -> list[dict[str, Any]]:
    """A coding-agent trace: each round is an assistant message with one or two
    tool calls, then their results, which average ``tool_output_chars`` chars."""
    rng = _Lcg(seed)
    corpus = _corpus()
    trace: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "You are a coding agent working in the acme repo.",
        },
        {
            "role": "user",
            "content": "Update every module to the new compute() API and keep the tests passing.",
        },
    ]
    for round_index in range(rounds):
        calls: list[dict[str, Any]] = [
            {
                "id": f"call_{round_index}_{call_index}",
                "type": "function",
                "function": {
                    "name": _pick_tool(rng),
                    "arguments": json.dumps(
                        {"path": f"src/module_{rng.below(60)}.py"}, ensure_ascii=False
                    ),
                },
            }
            for call_index in range(1 + rng.below(2))
        ]
        assistant: dict[str, Any] = {
            "role": "assistant",
            "content": None,
            "tool_calls": calls,
        }
        if rng.below(3) == 0:
            assistant["content"] = (
                f"Step {round_index}: checking module {rng.below(60)}."
            )
        if rng.below(4) == 0:
            start = rng.below(len(corpus) - 200)
            assistant["reasoning_content"] = (
                f"Round {round_index}: {corpus[start : start + 200]}"
            )
        trace.append(assistant)

        for call in calls:
            size = tool_output_chars // 4 + rng.below(tool_output_chars * 3 // 2 + 1)
            start = rng.below(len(corpus) - size)
            content = corpus[start : start + size]
            if call["function"]["name"] == "run_tests" and rng.below(2) == 0:
                content += f"\nFAILED tests/test_module.py::test_case_{round_index} - AssertionError"
            result: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": content,
            }
            if rng.below(25) == 0:
                result["is_error"] = True
            trace.append(result)

    trace.append(
        {
            "role": "assistant",
            "content": "Done. Every module uses the new compute() API and the tests pass.",
        }
    )
    return trace
