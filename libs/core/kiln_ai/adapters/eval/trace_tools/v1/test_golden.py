"""Golden tests freezing trace toolset v1's output.

To rewrite the expected files after a deliberate, reviewed change:
    uv run pytest libs/core/kiln_ai/adapters/eval/trace_tools/v1 --update-trace-tool-goldens
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kiln_ai.adapters.eval.trace_tools import judge_template_env
from kiln_ai.adapters.eval.trace_tools.v1 import TOOLSET_V1
from kiln_ai.adapters.eval.trace_tools.v1.conftest import GOLDEN_DIR, golden_trace
from kiln_ai.adapters.eval.trace_tools.v1.definitions import TOOL_DEFINITIONS
from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.tools import build_tools
from kiln_ai.adapters.eval.trace_tools.v1.view import build_view
from kiln_ai.tools.base_tool import KilnToolInterface

EXPECTED_DIR = GOLDEN_DIR / "expected"
DEFINITIONS_PATH = GOLDEN_DIR / "definitions.json"
CASES: list[dict[str, Any]] = json.loads(
    (GOLDEN_DIR / "cases.json").read_text(encoding="utf-8")
)
OVERVIEW_CASES = [case for case in CASES if case["tool"] == "trace_overview"]


def _read_expected(path: Path) -> str:
    # Stored with one trailing newline, so editors and git leave the files alone.
    return path.read_text(encoding="utf-8").removesuffix("\n")


def _write_expected(path: Path, text: str) -> None:
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def _check_golden(path: Path, actual: str, update: bool) -> None:
    if update:
        _write_expected(path, actual)
        return
    assert path.exists(), (
        f"Missing golden file {path.name}; run with --update-trace-tool-goldens"
    )
    assert actual == _read_expected(path)


@pytest.fixture(scope="module")
def tools_for() -> Callable[[str], dict[str, KilnToolInterface]]:
    built: dict[str, dict[str, KilnToolInterface]] = {}

    def tools(trace_name: str) -> dict[str, KilnToolInterface]:
        if trace_name not in built:
            view = build_view(golden_trace(trace_name))
            built[trace_name] = {
                definition.name: tool
                for definition, tool in zip(TOOL_DEFINITIONS, build_tools(view))
            }
        return built[trace_name]

    return tools


def test_case_ids_are_unique():
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_golden_cases(case, tools_for, update_goldens):
    tool = tools_for(case["trace"])[case["tool"]]
    try:
        output = (await tool.run(**case["args"])).output
        raised = False
    except TraceToolUsageError as e:
        output = str(e)
        raised = True

    assert raised == case.get("raises", False), output
    _check_golden(EXPECTED_DIR / f"{case['id']}.txt", output, update_goldens)


async def test_golden_definitions(update_goldens):
    definitions = [
        {"id": await tool.id(), **(await tool.toolcall_definition())}
        for tool in build_tools(build_view([]))
    ]
    _check_golden(
        DEFINITIONS_PATH,
        json.dumps(definitions, indent=2, ensure_ascii=False),
        update_goldens,
    )


@pytest.mark.parametrize(
    "case", OVERVIEW_CASES, ids=[c["trace"] for c in OVERVIEW_CASES]
)
def test_golden_overview_filter_matches_tool(case, update_goldens):
    if update_goldens:
        pytest.skip("Compares against goldens that test_golden_cases rewrites.")
    trace = golden_trace(case["trace"])
    env = judge_template_env(TOOLSET_V1, trace, None)
    rendered = env.from_string("{{ trace | trace_overview }}").render(trace=trace)
    assert rendered == _read_expected(EXPECTED_DIR / f"{case['id']}.txt")
