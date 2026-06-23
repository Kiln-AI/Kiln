"""Benchmarks for sandbox_worker / code-eval subprocess performance.

These benchmarks measure the end-to-end cost of spawning a child process
via ``run_scorer`` at various levels of code complexity.  With lazy
``__init__.py`` imports, the child process no longer loads the full
kiln_ai.adapters package chain, so ``run_scorer`` completes in tens of
milliseconds rather than seconds.

Marked ``@pytest.mark.slow`` so they are skipped in normal CI runs (requires
``--runslow`` to execute). Also marked ``@pytest.mark.benchmark`` for
categorisation; that marker does not skip tests — ``--benchmark-quiet`` only
suppresses benchmark output formatting.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kiln_ai.adapters.eval.sandbox_worker import run_scorer

_EVAL_HELPERS_PATH = Path(__file__).resolve().parent / "eval_helpers.py"

_INPUTS: dict = {
    "output": "hello world",
    "trace": None,
    "reference_data": None,
    "task_input": "test input",
}

TRIVIAL_CODE = (
    "def score(output, trace, reference_data, task_input):\n    return {'x': 1.0}\n"
)

STDLIB_IMPORT_CODE = (
    "import math\nimport json\nimport re\n"
    "def score(output, trace, reference_data, task_input):\n"
    "    return {'x': math.sqrt(4)}\n"
)

KILN_HELPERS_CODE = (
    "from kiln_ai.adapters.eval.eval_helpers import KilnEvalHelpers\n"
    "def score(output, trace, reference_data, task_input):\n"
    "    return {'x': KilnEvalHelpers.pass_fail(True)}\n"
)


# ---------------------------------------------------------------------------
# run_scorer benchmarks (multiprocessing.spawn with lazy __init__)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_run_scorer_trivial(benchmark):
    """Spawn + trivial scorer (return constant, no imports)."""

    def run():
        result = run_scorer(TRIVIAL_CODE, _INPUTS, timeout=30)
        assert "ok" in result

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Trivial scorer averaged {mean:.2f}s — expected under 0.5s"


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_run_scorer_stdlib_imports(benchmark):
    """Spawn + scorer that imports stdlib modules (math, json, re)."""

    def run():
        result = run_scorer(STDLIB_IMPORT_CODE, _INPUTS, timeout=30)
        assert "ok" in result

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Stdlib scorer averaged {mean:.2f}s — expected under 0.5s"


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_run_scorer_kiln_helpers(benchmark):
    """Spawn + scorer that uses KilnEvalHelpers (explicit import in scorer code)."""

    def run():
        result = run_scorer(KILN_HELPERS_CODE, _INPUTS, timeout=30)
        assert "ok" in result

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Kiln-helpers scorer averaged {mean:.2f}s — expected under 0.5s"


# ---------------------------------------------------------------------------
# Baseline: raw subprocess (no kiln_ai package imports in the child)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_raw_subprocess_baseline(benchmark):
    """Raw subprocess.run(python -c ...) executing the same trivial scorer.

    This measures the *achievable* floor: Python interpreter startup + exec
    of user code, with zero package imports in the child process.
    """
    wrapper = (
        "import sys, json; "
        "inputs = json.loads(sys.argv[1]); "
        "code = sys.argv[2]; "
        "ns = {}; exec(code, ns); "
        "r = ns['score'](output=inputs['output'], trace=inputs.get('trace'), "
        "reference_data=inputs.get('reference_data'), task_input=inputs['task_input']); "
        "print(json.dumps(r))"
    )
    inputs_json = json.dumps(_INPUTS)

    def run():
        proc = subprocess.run(
            [sys.executable, "-c", wrapper, inputs_json, TRIVIAL_CODE],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Raw subprocess averaged {mean:.2f}s — expected under 0.5s"


# ---------------------------------------------------------------------------
# Import-chain isolation: subprocess measuring only the import cost
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_import_chain_adapters(benchmark):
    """Subprocess that only does ``import kiln_ai.adapters``.

    With lazy __init__.py this should be fast (no transitive imports).
    """

    def run():
        proc = subprocess.run(
            [sys.executable, "-c", "import kiln_ai.adapters"],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, f"Import chain averaged {mean:.2f}s — expected under 0.5s"


@pytest.mark.benchmark
@pytest.mark.slow
def test_benchmark_import_eval_helpers_direct(benchmark):
    """Subprocess that imports eval_helpers by file path (no package chain).

    This shows the cost of the eval_helpers module itself, without the
    transitive kiln_ai.adapters package init.
    """
    import_stmt = (
        "import importlib.util; "
        "spec = importlib.util.spec_from_file_location('eval_helpers', "
        f"'{_EVAL_HELPERS_PATH}'); "
        "mod = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(mod)"
    )

    def run():
        proc = subprocess.run(
            [sys.executable, "-c", import_stmt],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0

    benchmark.pedantic(run, rounds=10, iterations=1)
    mean = benchmark.stats.stats.mean
    assert mean < 0.5, (
        f"Direct eval_helpers import averaged {mean:.2f}s — expected under 0.5s"
    )
