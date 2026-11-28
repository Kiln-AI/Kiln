"""A run's usage includes the sub-agents (Kiln task tools) it calls.

End to end and offline: real tasks, run configs, tool servers and adapters in a
temp project, with only the provider call replaced by a script.
"""

import asyncio
import json
from collections import deque
from pathlib import Path
from unittest.mock import patch

import litellm
import pytest
from litellm.types.utils import ModelResponse
from litellm.types.utils import Usage as LiteLlmUsage

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.eval_runner import EvalJob, EvalRunner
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
    TurnMode,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalInput,
    EvalInputSplit,
    EvalOutputScore,
    ExactMatchProperties,
    MultiTurnDriveConfig,
    MultiTurnSyntheticEvalInputData,
    SyntheticUserInfo,
    UserMessage,
)
from kiln_ai.datamodel.eval_splits import resolve_split
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.tool_id import build_kiln_task_tool_id
from kiln_ai.utils.config import Config
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam
from kiln_ai.utils.usage import MessageUsage


def reply(
    content: str | None = None,
    *,
    calls: tuple[tuple[str, str], ...] = (),
    cost: float | None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int | None = None,
) -> ModelResponse:
    """One provider response. `calls` are (tool_call_id, tool_name) pairs."""
    response = ModelResponse(
        model="gpt-4.1-mini",
        choices=[
            {
                "message": {
                    "content": content,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps({"input": "question"}),
                            },
                        }
                        for call_id, name in calls
                    ]
                    or None,
                }
            }
        ],
        usage=LiteLlmUsage(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            prompt_tokens_details=None
            if cached_tokens is None
            else {"cached_tokens": cached_tokens},
        ),
    )
    response._hidden_params["response_cost"] = cost
    return response


class ScriptedProvider:
    """Stands in for the provider: each agent answers from its own queue of replies.

    A request is routed by the task instruction in its system message, so a
    parent and the sub-agents it calls each follow their own script. A queued
    exception is raised in place of a reply.
    """

    def __init__(self) -> None:
        self._scripts: dict[str, deque[ModelResponse | Exception]] = {}
        self._delays: dict[str, float] = {}

    def script(
        self, task: Task, *replies: ModelResponse | Exception, delay_s: float = 0.0
    ) -> None:
        self.script_marker(task.instruction, *replies, delay_s=delay_s)

    def script_marker(
        self, marker: str, *replies: ModelResponse | Exception, delay_s: float = 0.0
    ) -> None:
        """Script the agent whose system message contains `marker`."""
        self._scripts[marker] = deque(replies)
        self._delays[marker] = delay_s

    def _agent(self, kwargs: dict) -> str:
        system_message = kwargs["messages"][0]["content"]
        matches = [i for i in self._scripts if i in system_message]
        assert len(matches) == 1, f"{len(matches)} scripts match: {system_message}"
        return matches[0]

    def _next_reply(self, agent: str) -> ModelResponse:
        assert self._scripts[agent], f"Script ran out of replies for: {agent}"
        next_reply = self._scripts[agent].popleft()
        if isinstance(next_reply, Exception):
            raise next_reply
        return next_reply

    def assert_all_used(self) -> None:
        unused = {agent: len(r) for agent, r in self._scripts.items() if r}
        assert not unused, f"Scripted replies never requested: {unused}"

    async def acompletion(self, **kwargs) -> ModelResponse:
        agent = self._agent(kwargs)
        await asyncio.sleep(self._delays[agent])
        return self._next_reply(agent)

    def streaming_completion(self, **kwargs) -> "_ScriptedStream":
        agent = self._agent(kwargs)
        return _ScriptedStream(self._next_reply(agent), self._delays[agent])


class _ScriptedStream:
    """The shape AdapterStream reads from StreamingCompletion: chunks, then a response."""

    def __init__(self, response: ModelResponse, delay_s: float) -> None:
        self.response = response
        self._delay_s = delay_s

    async def __aiter__(self):
        await asyncio.sleep(self._delay_s)
        return
        yield


class Agents:
    """A temp project of agents, where one agent can call another as a Kiln task tool."""

    def __init__(self, project_path: Path) -> None:
        self.project = Project(name="sub agents", path=project_path)
        self.project.save_to_file()
        # Kiln task tools resolve their project through the configured project list.
        Config.shared().save_setting("projects", [str(project_path)])
        self._run_configs: dict[str, TaskRunConfig] = {}

    def add(
        self,
        name: str,
        sub_agents: tuple[Task, ...] = (),
        turn_mode: TurnMode = TurnMode.single_turn,
    ) -> Task:
        """An agent that can call each of `sub_agents` as the tool `ask_<name>`."""
        task = Task(
            parent=self.project,
            name=name,
            instruction=f"You are the {name} agent.",
            turn_mode=turn_mode,
        )
        task.save_to_file()
        run_config = TaskRunConfig(
            parent=task,
            name=f"{name} config",
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt_4_1_mini",
                model_provider_name=ModelProviderName.openai,
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.json_schema,
                tools_config=ToolsRunConfig(
                    tools=[self._as_tool(sub_agent) for sub_agent in sub_agents]
                ),
            ),
        )
        run_config.save_to_file()
        assert task.id is not None
        self._run_configs[task.id] = run_config
        return task

    def _as_tool(self, task: Task) -> str:
        server = ExternalToolServer(
            parent=self.project,
            name=f"{task.name} tool",
            type=ToolServerType.kiln_task,
            description=f"Ask the {task.name} agent",
            properties={
                "name": f"ask_{task.name}",
                "description": f"Ask the {task.name} agent",
                "task_id": task.id,
                "run_config_id": self.run_config(task).id,
                "is_archived": False,
            },
        )
        server.save_to_file()
        return build_kiln_task_tool_id(server.id)

    def run_config(self, task: Task) -> TaskRunConfig:
        assert task.id is not None
        return self._run_configs[task.id]

    def adapter(self, task: Task, allow_saving: bool = True) -> BaseAdapter:
        run_config = self.run_config(task)
        return adapter_for_task(
            task,
            run_config_properties=run_config.run_config_properties,
            base_adapter_config=AdapterConfig(
                allow_saving=allow_saving, task_run_config_id=run_config.id
            ),
        )


@pytest.fixture
def agents(tmp_path) -> Agents:
    return Agents(tmp_path / "project.kiln")


@pytest.fixture
def provider():
    scripted = ScriptedProvider()
    # An OpenAI adapter can't be built without a key. A fake one keeps these
    # tests independent of the machine's keys, and unable to spend on a real one.
    Config.shared().save_setting("open_ai_api_key", "fake-key-for-offline-tests")
    with (
        patch("litellm.acompletion", new=scripted.acompletion),
        patch(
            "kiln_ai.adapters.model_adapters.adapter_stream.StreamingCompletion",
            new=scripted.streaming_completion,
        ),
    ):
        yield scripted
    scripted.assert_all_used()


async def run_agent(
    adapter: BaseAdapter,
    input: str,
    streamed: bool,
    prior_trace: list[ChatCompletionMessageParam] | None = None,
) -> TaskRun:
    if not streamed:
        return await adapter.invoke(input, prior_trace=prior_trace)
    stream = adapter.invoke_openai_stream(input, prior_trace=prior_trace)
    async for _ in stream:
        pass
    return stream.task_run


streamed_or_not = pytest.mark.parametrize(
    "streamed", [False, True], ids=["invoked", "streamed"]
)


def tool_messages(run: TaskRun) -> list[dict]:
    assert run.trace is not None
    return [dict(m) for m in run.trace if m["role"] == "tool"]


def own_latency_ms(run: TaskRun) -> int:
    assert run.trace is not None
    return sum(m.get("latency_ms", 0) for m in run.trace if m["role"] == "assistant")


def assert_usage(
    usage: MessageUsage | None,
    *,
    cost: float | None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int | None = None,
) -> None:
    assert usage is not None
    assert usage.cost == (None if cost is None else pytest.approx(cost))
    assert usage.input_tokens == input_tokens
    assert usage.output_tokens == output_tokens
    assert usage.total_tokens == input_tokens + output_tokens
    assert usage.cached_tokens == cached_tokens


ONE_CALL_TOTAL = {"cost": 0.013, "input_tokens": 1220, "output_tokens": 65}


@pytest.fixture
def one_sub_agent_call(agents, provider) -> tuple[Task, Task]:
    """A parent that calls its child once; the run costs ONE_CALL_TOTAL."""
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"),), cost=0.001, input_tokens=100, output_tokens=10
        ),
        reply("hello", cost=0.002, input_tokens=120, output_tokens=5),
    )
    provider.script(
        child,
        reply("child answer", cost=0.01, input_tokens=1000, output_tokens=50),
        delay_s=0.02,
    )
    return parent, child


@streamed_or_not
async def test_run_includes_its_sub_agent_call(agents, one_sub_agent_call, streamed):
    parent, child = one_sub_agent_call

    run = await run_agent(agents.adapter(parent), "go", streamed)

    assert_usage(run.usage, **ONE_CALL_TOTAL)
    assert_usage(run.cumulative_usage, **ONE_CALL_TOTAL)

    # The sub-agent's run is saved under its own task, and the parent's tool
    # message points at it and carries what it spent.
    (child_run,) = child.runs()
    assert child_run.tags == ["tool_call"]
    assert_usage(child_run.usage, cost=0.01, input_tokens=1000, output_tokens=50)
    (tool_message,) = tool_messages(run)
    assert tool_message["kiln_task_tool_data"].endswith(f":::{child_run.id}")
    assert tool_message["usage"] == MessageUsage(
        input_tokens=1000, output_tokens=50, total_tokens=1050, cost=0.01
    )

    # Latency stays the parent's own model calls: the child's is not added.
    assert child_run.usage is not None and run.usage is not None
    assert child_run.usage.total_llm_latency_ms > 0
    assert run.usage.total_llm_latency_ms == own_latency_ms(run)

    # The saved file keeps the per-message usage, so the total can be re-derived.
    assert run.path is not None
    reloaded = TaskRun.load_from_file(run.path)
    assert_usage(reloaded.usage, **ONE_CALL_TOTAL)
    assert_usage(MessageUsage.from_trace(reloaded.trace), **ONE_CALL_TOTAL)


@streamed_or_not
async def test_each_call_is_counted_once_when_a_tool_is_called_several_times(
    agents, provider, streamed
):
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"), ("c2", "ask_child")),
            cost=0.001,
            input_tokens=100,
            output_tokens=10,
        ),
        reply(
            calls=(("c3", "ask_child"),), cost=0.002, input_tokens=200, output_tokens=20
        ),
        reply("done", cost=0.004, input_tokens=400, output_tokens=40),
    )
    provider.script(
        child,
        reply("one", cost=0.01, input_tokens=1000, output_tokens=1),
        reply("two", cost=0.02, input_tokens=2000, output_tokens=2),
        reply("three", cost=0.04, input_tokens=4000, output_tokens=4),
    )

    run = await run_agent(agents.adapter(parent), "go", streamed)

    assert sorted(m["usage"].cost for m in tool_messages(run)) == [0.01, 0.02, 0.04]
    total = {"cost": 0.077, "input_tokens": 7700, "output_tokens": 77}
    assert_usage(run.usage, **total)
    assert_usage(run.cumulative_usage, **total)
    assert len(child.runs()) == 3


@streamed_or_not
async def test_nested_sub_agents_are_counted_once(agents, provider, streamed):
    grandchild = agents.add("grandchild")
    child = agents.add("child", sub_agents=(grandchild,))
    parent = agents.add("parent", sub_agents=(child,))
    provider.script(
        parent,
        reply(
            calls=(("p1", "ask_child"),), cost=0.001, input_tokens=100, output_tokens=1
        ),
        reply("done", cost=0.002, input_tokens=200, output_tokens=2),
    )
    provider.script(
        child,
        reply(
            calls=(("k1", "ask_grandchild"),),
            cost=0.01,
            input_tokens=1000,
            output_tokens=10,
            cached_tokens=500,
        ),
        reply("child answer", cost=0.02, input_tokens=2000, output_tokens=20),
    )
    provider.script(
        grandchild,
        reply(
            "grandchild answer",
            cost=0.1,
            input_tokens=10000,
            output_tokens=100,
            cached_tokens=4000,
        ),
    )

    run = await run_agent(agents.adapter(parent), "go", streamed)

    grandchild_total = {
        "cost": 0.1,
        "input_tokens": 10000,
        "output_tokens": 100,
        "cached_tokens": 4000,
    }
    child_total = {
        "cost": 0.13,
        "input_tokens": 13000,
        "output_tokens": 130,
        "cached_tokens": 4500,
    }
    parent_total = {
        "cost": 0.133,
        "input_tokens": 13300,
        "output_tokens": 133,
        "cached_tokens": 4500,
    }

    assert_usage(run.usage, **parent_total)
    assert_usage(run.cumulative_usage, **parent_total)
    # The parent sees one figure for the child's whole subtree.
    (parent_tool_message,) = tool_messages(run)
    assert_usage(parent_tool_message["usage"], **child_total)

    (child_run,) = child.runs()
    assert_usage(child_run.usage, **child_total)
    (child_tool_message,) = tool_messages(child_run)
    assert_usage(child_tool_message["usage"], **grandchild_total)

    (grandchild_run,) = grandchild.runs()
    assert_usage(grandchild_run.usage, **grandchild_total)


@streamed_or_not
@pytest.mark.parametrize(
    "parent_cost, child_cost, expected_cost",
    [
        pytest.param(0.001, None, 0.002, id="sub_agent_cost_unknown"),
        pytest.param(None, 0.01, 0.01, id="parent_cost_unknown"),
        pytest.param(None, None, None, id="all_costs_unknown"),
    ],
)
async def test_unknown_cost_is_left_out_of_the_sum_not_counted_as_zero(
    agents, provider, parent_cost, child_cost, expected_cost, streamed
):
    """The same rule as two model calls in one run: a cost the provider did not
    report adds nothing, and a run where nothing was reported has no cost at all."""
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"),),
            cost=parent_cost,
            input_tokens=100,
            output_tokens=10,
        ),
        reply("done", cost=parent_cost, input_tokens=120, output_tokens=5),
    )
    provider.script(
        child,
        reply("child answer", cost=child_cost, input_tokens=1000, output_tokens=50),
    )

    run = await run_agent(agents.adapter(parent), "go", streamed)

    total = {"cost": expected_cost, "input_tokens": 1220, "output_tokens": 65}
    assert_usage(run.usage, **total)
    assert_usage(run.cumulative_usage, **total)


def parent_calls_child_once(provider: ScriptedProvider, parent: Task) -> None:
    """The parent asks its child once, then answers; its own calls cost 0.003."""
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"),), cost=0.001, input_tokens=100, output_tokens=10
        ),
        reply("done", cost=0.002, input_tokens=120, output_tokens=5),
    )


PARENT_OWN = {"cost": 0.003, "input_tokens": 220, "output_tokens": 15}


@streamed_or_not
async def test_a_sub_agent_that_fails_before_spending_adds_no_usage(
    agents, provider, streamed
):
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    parent_calls_child_once(provider, parent)
    provider.script(child, RuntimeError("the child's provider failed"))

    run = await run_agent(agents.adapter(parent), "go", streamed)

    (tool_message,) = tool_messages(run)
    assert tool_message["is_error"] is True
    assert "usage" not in tool_message
    assert_usage(run.usage, **PARENT_OWN)
    assert_usage(run.cumulative_usage, **PARENT_OWN)


@streamed_or_not
async def test_a_sub_agent_that_fails_after_a_paid_call_adds_that_spend(
    agents, provider, streamed
):
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    parent_calls_child_once(provider, parent)
    provider.script(
        child,
        # A call to a tool the child doesn't have gets an error result, so the
        # child makes a second model call, which fails.
        reply(
            calls=(("k1", "no_such_tool"),),
            cost=0.01,
            input_tokens=1000,
            output_tokens=10,
        ),
        RuntimeError("the child's provider failed"),
    )

    run = await run_agent(agents.adapter(parent), "go", streamed)

    (tool_message,) = tool_messages(run)
    assert tool_message["is_error"] is True
    assert_usage(tool_message["usage"], cost=0.01, input_tokens=1000, output_tokens=10)
    total = {"cost": 0.013, "input_tokens": 1220, "output_tokens": 25}
    assert_usage(run.usage, **total)
    assert_usage(run.cumulative_usage, **total)


async def test_a_sub_agent_that_fails_after_a_grandchild_call_adds_both(
    agents, provider
):
    grandchild = agents.add("grandchild")
    child = agents.add("child", sub_agents=(grandchild,))
    parent = agents.add("parent", sub_agents=(child,))
    parent_calls_child_once(provider, parent)
    provider.script(
        child,
        reply(
            calls=(("k1", "ask_grandchild"),),
            cost=0.01,
            input_tokens=1000,
            output_tokens=10,
        ),
        RuntimeError("the child's provider failed"),
    )
    provider.script(
        grandchild,
        reply("grandchild answer", cost=0.1, input_tokens=10000, output_tokens=100),
    )

    run = await run_agent(agents.adapter(parent), "go", streamed=False)

    (tool_message,) = tool_messages(run)
    assert tool_message["is_error"] is True
    assert_usage(
        tool_message["usage"], cost=0.11, input_tokens=11000, output_tokens=110
    )
    total = {"cost": 0.113, "input_tokens": 11220, "output_tokens": 125}
    assert_usage(run.usage, **total)
    assert_usage(run.cumulative_usage, **total)


async def test_a_run_ending_sub_agent_error_still_fails_the_parent(agents, provider):
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"),), cost=0.001, input_tokens=100, output_tokens=10
        ),
    )
    provider.script(
        child,
        litellm.RateLimitError(
            message="slow down", llm_provider="openai", model="gpt-4.1-mini"
        ),
    )

    with pytest.raises(KilnRunError):
        await run_agent(agents.adapter(parent), "go", streamed=False)


@streamed_or_not
async def test_continued_conversation_keeps_earlier_sub_agent_calls_in_cumulative_usage(
    agents, provider, streamed
):
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"),), cost=0.001, input_tokens=100, output_tokens=1
        ),
        reply("first answer", cost=0.002, input_tokens=200, output_tokens=2),
        reply(
            calls=(("c2", "ask_child"),), cost=0.004, input_tokens=400, output_tokens=4
        ),
        reply("second answer", cost=0.008, input_tokens=800, output_tokens=8),
    )
    provider.script(
        child,
        reply("one", cost=0.01, input_tokens=1000, output_tokens=10),
        reply("two", cost=0.02, input_tokens=2000, output_tokens=20),
    )

    first = await run_agent(agents.adapter(parent), "go", streamed)
    # Continue from the saved file, as the API does: its usage values are dicts.
    assert first.path is not None
    saved_trace = TaskRun.load_from_file(first.path).trace
    second = await run_agent(
        agents.adapter(parent), "go on", streamed, prior_trace=saved_trace
    )

    # `usage` is this turn only; `cumulative_usage` is the whole conversation.
    assert_usage(second.usage, cost=0.032, input_tokens=3200, output_tokens=32)
    assert_usage(
        second.cumulative_usage, cost=0.045, input_tokens=4500, output_tokens=45
    )


async def test_eval_job_run_includes_a_sub_agent_whose_run_is_not_saved(
    agents, one_sub_agent_call
):
    parent, child = one_sub_agent_call
    says_hello_eval = Eval(
        parent=parent,
        name="says hello",
        eval_set_filter_id="all",
        eval_configs_filter_id="all",
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Is the output hello",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    says_hello_eval.save_to_file()
    eval_config = EvalConfig(
        parent=says_hello_eval,
        name="exact match",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="hello"),
    )
    eval_config.save_to_file()
    item = TaskRun(
        parent=parent,
        input="go",
        output=TaskOutput(
            output="dataset output",
            source=DataSource(
                type=DataSourceType.human, properties={"created_by": "tester"}
            ),
        ),
    )
    item.save_to_file()
    split = resolve_split(parent, says_hello_eval, "test")
    assert split is not None
    runner = EvalRunner(
        eval_configs=[eval_config],
        run_configs=[agents.run_config(parent)],
        eval_run_type="task_run_eval",
        split=split,
    )

    await runner.run_job(
        EvalJob(
            item=item,
            eval_config=eval_config,
            type="task_run_eval",
            task_run_config=agents.run_config(parent),
        )
    )

    (eval_run,) = eval_config.runs()
    assert eval_run.scores == {"accuracy": 1.0}
    (scored_run,) = [
        run
        for run in parent.runs(include_eval_generated=True)
        if run.id == eval_run.scored_run_id
    ]
    assert_usage(scored_run.usage, **ONE_CALL_TOTAL)
    assert_usage(scored_run.cumulative_usage, **ONE_CALL_TOTAL)

    # An eval job saves no run for the sub-agent, so the parent's trace is the
    # only record of what the sub-agent spent.
    assert child.runs() == []
    (tool_message,) = tool_messages(scored_run)
    assert tool_message["kiln_task_tool_data"].endswith(":::None")
    assert_usage(tool_message["usage"], cost=0.01, input_tokens=1000, output_tokens=50)


async def test_multi_turn_eval_drive_includes_the_sub_agent_but_not_the_synthetic_user(
    agents, provider
):
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,), turn_mode=TurnMode.multiturn)
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"),), cost=0.001, input_tokens=100, output_tokens=10
        ),
        reply("first answer", cost=0.002, input_tokens=120, output_tokens=5),
        reply("second answer", cost=0.004, input_tokens=400, output_tokens=40),
    )
    provider.script(
        child,
        reply("child answer", cost=0.01, input_tokens=1000, output_tokens=50),
    )
    # The synthetic user's system prompt names its persona.
    provider.script_marker(
        "a customer who wants a refund",
        reply("and the refund?", cost=0.5, input_tokens=50000, output_tokens=500),
    )
    Config.shared().save_setting("open_router_api_key", "fake-key-for-offline-tests")

    redrive_eval = Eval(
        parent=parent,
        name="multi turn",
        splits={"test": EvalInputSplit(filter_id="all")},
        eval_configs_filter_id="all",
        evaluation_data_type=EvalDataType.full_trace,
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Is the last answer right",
                type=TaskOutputRatingType.pass_fail,
            )
        ],
    )
    redrive_eval.save_to_file()
    eval_config = EvalConfig(
        parent=redrive_eval,
        name="exact match",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="second answer"),
    )
    eval_config.save_to_file()
    item = EvalInput(
        parent=parent,
        data=MultiTurnSyntheticEvalInputData(
            first_message=UserMessage(text="I want my money back"),
            synthetic_user_info=SyntheticUserInfo(
                persona="a customer who wants a refund", goal="get a refund"
            ),
            drive_config=MultiTurnDriveConfig(
                model_name="claude_4_5_haiku", model_provider="openrouter", turns=2
            ),
        ),
    )
    item.save_to_file()
    split = resolve_split(parent, redrive_eval, "test")
    assert split is not None
    runner = EvalRunner(
        eval_configs=[eval_config],
        run_configs=[agents.run_config(parent)],
        eval_run_type="task_run_eval",
        split=split,
    )

    await runner.run_job(
        EvalJob(
            item=item,
            eval_config=eval_config,
            type="task_run_eval",
            task_run_config=agents.run_config(parent),
        )
    )

    (eval_run,) = eval_config.runs()
    assert eval_run.skipped_reason is None
    (scored_run,) = [
        run
        for run in parent.runs(include_eval_generated=True)
        if run.id == eval_run.scored_run_id
    ]
    # The agent's three calls and its sub-agent, both turns.
    agent_total = {"cost": 0.017, "input_tokens": 1620, "output_tokens": 105}
    assert_usage(scored_run.usage, **agent_total)
    assert_usage(scored_run.cumulative_usage, **agent_total)
    # The synthetic user is not part of the agent, so it stays on its own field.
    assert scored_run.synthetic_user_usage is not None
    assert scored_run.synthetic_user_usage.cost == pytest.approx(0.5)
    assert scored_run.synthetic_user_usage.input_tokens == 50000
