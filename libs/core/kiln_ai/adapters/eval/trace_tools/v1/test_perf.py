"""Benchmarks on a synthetic 20 MB trace (about 5M tokens, 10,000 messages).

The bounds are the performance targets for the trace tools. Local runs are
about ten times faster, which leaves room for slow, parallel CI machines.
Timing is measured here rather than read from pytest-benchmark, which turns
itself off under xdist.
"""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from kiln_ai.adapters.eval.trace_tools.v1.conftest import synthetic_coding_trace
from kiln_ai.adapters.eval.trace_tools.v1.errors import TraceToolUsageError
from kiln_ai.adapters.eval.trace_tools.v1.render import PreviewArgs, preview_messages
from kiln_ai.adapters.eval.trace_tools.v1.search import SearchArgs, search_trace
from kiln_ai.adapters.eval.trace_tools.v1.view import TraceView, build_view

BUILD_VIEW_SECONDS = 2.0
TOOL_SECONDS = 0.2
SEARCH_SECONDS = 2.0
PARALLEL_SEARCHES = 4
PARALLEL_SEARCH_SECONDS = 10.0


@pytest.fixture(scope="module")
def large_trace() -> list[dict[str, Any]]:
    trace = synthetic_coding_trace(rounds=4_000, tool_output_chars=3_400)
    assert sum(len(m.get("content") or "") for m in trace) > 20_000_000
    return trace


@pytest.fixture(scope="module")
def large_view(large_trace) -> TraceView:
    return build_view(large_trace)


def _fastest_seconds(benchmark, target: Callable[[], Any]) -> tuple[Any, float]:
    durations: list[float] = []
    result = None

    def timed() -> None:
        nonlocal result
        started = time.perf_counter()
        result = target()
        durations.append(time.perf_counter() - started)

    benchmark.pedantic(timed, rounds=3, iterations=1)
    return result, min(durations)


@pytest.mark.benchmark
def test_bench_build_view_20mb(benchmark, large_trace):
    view, seconds = _fastest_seconds(benchmark, lambda: build_view(large_trace))
    assert view.count == len(large_trace)
    assert seconds < BUILD_VIEW_SECONDS


@pytest.mark.benchmark
def test_bench_preview_whole_trace_refused_20mb(benchmark, large_view):
    def preview_whole_trace() -> str:
        try:
            preview_messages(large_view, PreviewArgs(preview_chars=0))
        except TraceToolUsageError as e:
            return str(e)
        raise AssertionError("A 10,000 message preview should be refused")

    refusal, seconds = _fastest_seconds(benchmark, preview_whole_trace)
    assert "fit at these settings" in refusal
    assert seconds < TOOL_SECONDS


@pytest.mark.benchmark
def test_bench_search_20mb(benchmark, large_view):
    output, seconds = _fastest_seconds(
        benchmark, lambda: search_trace(large_view, SearchArgs(pattern="FAILED tests"))
    )
    assert output.split()[1] == "matches"
    assert seconds < SEARCH_SECONDS


@pytest.mark.benchmark
def test_bench_parallel_literal_searches_20mb(benchmark, large_view):
    # A judge's parallel tool calls run their searches in threads at once.
    # "compute" matches hundreds of thousands of times in this trace, and a
    # search that releases the GIL while matching hands it off once per match.
    args = SearchArgs(pattern="compute")

    def search_in_parallel() -> list[str]:
        with ThreadPoolExecutor(max_workers=PARALLEL_SEARCHES) as pool:
            searches = [
                pool.submit(search_trace, large_view, args)
                for _ in range(PARALLEL_SEARCHES)
            ]
            return [search.result() for search in searches]

    outputs, seconds = _fastest_seconds(benchmark, search_in_parallel)
    assert outputs[0].split()[1] == "matches"
    assert outputs == [search_trace(large_view, args)] * PARALLEL_SEARCHES
    assert seconds < PARALLEL_SEARCH_SECONDS
