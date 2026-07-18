"""Code-eval bridge integration tests (arch §6 "Code-eval bridge").

These SPAWN real child processes and exercise the full nested-tool bridge:
a user ``score()`` calls ``tools.llm`` / ``tools.llm_judge`` (which run parent-side,
so patching ``adapter_for_task`` in THIS process works across the process boundary),
allowlist enforcement, timeouts, and real parallelism (regression against the deleted
global execution lock).
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiln_ai.adapters.eval.v2_eval_code_eval import (
    CodeEvalAdapter,
    _trusted_projects,
    grant_code_eval_trust,
)
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

# run_llm_call resolves adapter_for_task function-locally from adapter_registry, so
# patch it at its definition site. The LLM tool runs parent-side, so this patch is
# effective even though score() runs in a spawned child.
ADAPTER_PATH = "kiln_ai.adapters.adapter_registry.adapter_for_task"
PROJECT_PATH = "/fake/project/path"

PF = TaskOutputRatingType.pass_fail


@pytest.fixture(autouse=True)
def _clear_trust():
    _trusted_projects.clear()
    yield
    _trusted_projects.clear()


def _score(name: str, typ: TaskOutputRatingType = PF) -> EvalOutputScore:
    return EvalOutputScore(name=name, instruction=f"Score: {name}", type=typ)


def _make_config(
    code: str,
    output_scores: list[EvalOutputScore] | None = None,
    tool_allowlist: list[str] | None = None,
    timeout: int = 30,
) -> EvalConfig:
    props = CodeEvalProperties(
        code=code,
        timeout_seconds=timeout,
        tool_allowlist=tool_allowlist or [],
    )
    parent_eval = Mock()
    parent_eval.output_scores = output_scores or [_score("Accuracy")]
    parent_task = Mock()
    parent_project = Mock()
    parent_project.id = "project-bridge-tests"
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


def _patch_adapter(run_output: RunOutput):
    """Return a Mock standing in for ``adapter_for_task`` -> adapter."""
    adapter = AsyncMock()
    adapter.invoke_returning_run_output.return_value = (Mock(), run_output)
    return Mock(return_value=adapter)


# ---------------------------------------------------------------------------
# tools.llm_judge from score()
# ---------------------------------------------------------------------------


class TestLlmJudgeFromScore:
    @pytest.mark.asyncio
    async def test_llm_judge_scores_route_back(self):
        code = (
            "import json\n"
            "from kiln import tools\n"
            "def score(output):\n"
            "    raw = tools.llm_judge(\n"
            "        prompt='Judge: {{ text }}',\n"
            "        model='gpt_4o', provider='openai',\n"
            "        input={'text': output},\n"
            "    )\n"
            "    return json.loads(raw)\n"
        )
        cfg = _make_config(
            code,
            output_scores=[_score("Accuracy")],
            tool_allowlist=[KilnBuiltInToolId.LLM_JUDGE],
        )
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        factory = _patch_adapter(
            RunOutput(output={"accuracy": "pass"}, intermediate_outputs=None)
        )
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(_inp(final_message="answer text"))

        assert result.skipped_reason is None
        assert result.scores == {"accuracy": 1.0}
        # The eval's own (allow_float_scores=False) schema flowed into the model call.
        task_arg = factory.call_args[0][0]
        assert task_arg.output_json_schema is not None


# ---------------------------------------------------------------------------
# tools.llm from score()
# ---------------------------------------------------------------------------


class TestLlmFromScore:
    @pytest.mark.asyncio
    async def test_llm_free_text(self):
        code = (
            "from kiln import tools\n"
            "def score(output):\n"
            "    resp = tools.llm(\n"
            "        prompt='Q: {{ text }}', model='gpt_4o', provider='openai',\n"
            "        input={'text': output},\n"
            "    )\n"
            "    return {'accuracy': 1.0 if resp == 'YES' else 0.0}\n"
        )
        cfg = _make_config(code, tool_allowlist=[KilnBuiltInToolId.LLM])
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        factory = _patch_adapter(RunOutput(output="YES", intermediate_outputs=None))
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(_inp(final_message="q"))

        assert result.skipped_reason is None
        assert result.scores == {"accuracy": 1.0}

    @pytest.mark.asyncio
    async def test_llm_structured_output(self):
        code = (
            "import json\n"
            "from kiln import tools\n"
            "def score(output):\n"
            "    resp = tools.llm(\n"
            "        prompt='x', model='gpt_4o', provider='openai',\n"
            "        schema={'type': 'object',\n"
            "                'properties': {'verdict': {'type': 'string'}},\n"
            "                'required': ['verdict']},\n"
            "    )\n"
            "    data = json.loads(resp)\n"
            "    return {'accuracy': 1.0 if data['verdict'] == 'good' else 0.0}\n"
        )
        cfg = _make_config(code, tool_allowlist=[KilnBuiltInToolId.LLM])
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        factory = _patch_adapter(
            RunOutput(output={"verdict": "good"}, intermediate_outputs=None)
        )
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(_inp())

        assert result.scores == {"accuracy": 1.0}


# ---------------------------------------------------------------------------
# sync + async def score
# ---------------------------------------------------------------------------


class TestSyncAndAsyncScore:
    @pytest.mark.asyncio
    async def test_sync_score_with_llm(self):
        code = (
            "from kiln import tools\n"
            "def score(output):\n"
            "    resp = tools.llm(prompt='x', model='gpt_4o', provider='openai')\n"
            "    return {'accuracy': 1.0 if resp == 'OK' else 0.0}\n"
        )
        cfg = _make_config(code, tool_allowlist=[KilnBuiltInToolId.LLM])
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        factory = _patch_adapter(RunOutput(output="OK", intermediate_outputs=None))
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(_inp())

        assert result.scores == {"accuracy": 1.0}

    @pytest.mark.asyncio
    async def test_async_score_gather_two_llm_calls(self):
        code = (
            "import asyncio\n"
            "from kiln import async_tools\n"
            "async def score(output):\n"
            "    a, b = await asyncio.gather(\n"
            "        async_tools.llm(prompt='a', model='gpt_4o', provider='openai'),\n"
            "        async_tools.llm(prompt='b', model='gpt_4o', provider='openai'),\n"
            "    )\n"
            "    return {'accuracy': 1.0 if a == 'OK' and b == 'OK' else 0.0}\n"
        )
        cfg = _make_config(code, tool_allowlist=[KilnBuiltInToolId.LLM])
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        factory = _patch_adapter(RunOutput(output="OK", intermediate_outputs=None))
        with patch(ADAPTER_PATH, factory):
            result = await adapter.evaluate(_inp())

        assert result.scores == {"accuracy": 1.0}


# ---------------------------------------------------------------------------
# Allowlist enforcement
# ---------------------------------------------------------------------------


class TestAllowlistEnforcement:
    @pytest.mark.asyncio
    async def test_not_allowlisted_tool_raises_tool_not_allowed(self):
        # llm is allowlisted; llm_judge is NOT.
        code = (
            "from kiln import tools\n"
            "from kiln.tools import ToolNotAllowed\n"
            "def score(output):\n"
            "    try:\n"
            "        tools.llm_judge(prompt='x', model='gpt_4o', provider='openai')\n"
            "    except ToolNotAllowed:\n"
            "        return {'accuracy': 0.0}\n"
            "    return {'accuracy': 1.0}\n"
        )
        cfg = _make_config(code, tool_allowlist=[KilnBuiltInToolId.LLM])
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        result = await adapter.evaluate(_inp())
        # 0.0 == the ToolNotAllowed branch was taken.
        assert result.scores == {"accuracy": 0.0}


# ---------------------------------------------------------------------------
# Timeout mid-LLM-call
# ---------------------------------------------------------------------------


class TestTimeoutMidCall:
    @pytest.mark.asyncio
    async def test_timeout_kills_child_during_llm_call(self):
        code = (
            "from kiln import tools\n"
            "def score(output):\n"
            "    tools.llm(prompt='x', model='gpt_4o', provider='openai')\n"
            "    return {'accuracy': 1.0}\n"
        )
        cfg = _make_config(code, tool_allowlist=[KilnBuiltInToolId.LLM], timeout=1)
        adapter = CodeEvalAdapter(cfg)
        grant_code_eval_trust(PROJECT_PATH)

        async def _hang(*_args, **_kwargs):
            await asyncio.sleep(30)

        hanging_adapter = Mock()
        hanging_adapter.invoke_returning_run_output = _hang
        factory = Mock(return_value=hanging_adapter)

        with patch(ADAPTER_PATH, factory):
            with pytest.raises(RuntimeError, match="timed out"):
                await adapter.evaluate(_inp())


# ---------------------------------------------------------------------------
# Parallelism (regression against the deleted global lock)
# ---------------------------------------------------------------------------


class TestParallelism:
    @pytest.mark.asyncio
    async def test_parallel_code_evals_run_concurrently(self):
        """N code evals run concurrently — wall-clock << sum of per-item sleeps.

        With the old global asyncio.Lock these would serialize; the shared depth-0
        semaphore (16 slots) lets them overlap.
        """
        per_sleep = 0.6
        n = 3
        code = (
            "import time\n"
            "def score(output):\n"
            f"    time.sleep({per_sleep})\n"
            "    return {'accuracy': 1.0}\n"
        )
        grant_code_eval_trust(PROJECT_PATH)
        adapters = [CodeEvalAdapter(_make_config(code)) for _ in range(n)]

        start = time.perf_counter()
        results = await asyncio.gather(*(a.evaluate(_inp()) for a in adapters))
        elapsed = time.perf_counter() - start

        assert all(r.scores == {"accuracy": 1.0} for r in results)
        serial_lower_bound = n * per_sleep  # 1.8s
        assert elapsed < serial_lower_bound, (
            f"Expected concurrent execution (< {serial_lower_bound}s), got {elapsed:.2f}s"
        )
        # Even with spawn overhead, real parallelism saves well over one full sleep.
        assert elapsed < serial_lower_bound - per_sleep


# ---------------------------------------------------------------------------
# Shared-lock / semaphore identity
# ---------------------------------------------------------------------------


class TestSharedInfrastructureIdentity:
    @pytest.mark.asyncio
    async def test_code_tools_and_evals_share_bridge_lock_and_semaphore(self):
        from kiln_ai.adapters.eval import v2_eval_code_eval
        from kiln_ai.sandbox import spawn
        from kiln_ai.tools import code_tool, sandbox_bridge

        # Both call sites resolve to the one shared run_bridged_child.
        assert code_tool.run_bridged_child is sandbox_bridge.run_bridged_child
        assert v2_eval_code_eval.run_bridged_child is sandbox_bridge.run_bridged_child

        # One shared spawn helper (hence one shared _spawn_lock) across both paths.
        assert (
            sandbox_bridge.start_process_with_light_main
            is spawn.start_process_with_light_main
        )

        # One shared, lazily-created semaphore.
        sem_a = await sandbox_bridge._get_semaphore()
        sem_b = await sandbox_bridge._get_semaphore()
        assert sem_a is sem_b
        assert sandbox_bridge._semaphore is sem_a
