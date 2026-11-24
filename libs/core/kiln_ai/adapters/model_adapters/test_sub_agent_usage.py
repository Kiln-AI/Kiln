"""A run's usage includes the sub-agents (Kiln task tools) it calls.

End to end and offline: real tasks, run configs, tool servers and adapters in a
temp project, with only the provider call replaced by a script.
"""

import json
from collections import deque
from pathlib import Path
from unittest.mock import patch

import pytest
from litellm.types.utils import ModelResponse
from litellm.types.utils import Usage as LiteLlmUsage

from kiln_ai.adapters.adapter_registry import adapter_for_task
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
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    ExactMatchProperties,
)
from kiln_ai.datamodel.eval_splits import resolve_split
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.tool_id import build_kiln_task_tool_id
from kiln_ai.utils.config import Config
from kiln_ai.utils.usage import MessageUsage


def reply(
    content: str | None = None,
    *,
    calls: tuple[tuple[str, str], ...] = (),
    cost: float | None,
    input_tokens: int,
    output_tokens: int,
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
        ),
    )
    response._hidden_params["response_cost"] = cost
    return response


class ScriptedProvider:
    """Stands in for the provider: each agent answers from its own queue of replies.

    A request is routed by the task instruction in its system message, so a
    parent and the sub-agents it calls each follow their own script.
    """

    def __init__(self) -> None:
        self._scripts: dict[str, deque[ModelResponse]] = {}

    def script(self, task: Task, *replies: ModelResponse) -> None:
        self._scripts[task.instruction] = deque(replies)

    def next_reply(self, **kwargs) -> ModelResponse:
        system_message = kwargs["messages"][0]["content"]
        for instruction, replies in self._scripts.items():
            if instruction in system_message:
                return replies.popleft()
        raise AssertionError(f"No script for system message: {system_message}")

    async def acompletion(self, **kwargs) -> ModelResponse:
        return self.next_reply(**kwargs)

    def streaming_completion(self, **kwargs) -> "_ScriptedStream":
        return _ScriptedStream(self.next_reply(**kwargs))


class _ScriptedStream:
    """The shape AdapterStream reads from StreamingCompletion: chunks, then a response."""

    def __init__(self, response: ModelResponse) -> None:
        self.response = response

    async def __aiter__(self):
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

    def add(self, name: str, sub_agents: tuple[Task, ...] = ()) -> Task:
        """An agent that can call each of `sub_agents` as the tool `ask_<name>`."""
        task = Task(
            parent=self.project,
            name=name,
            instruction=f"You are the {name} agent.",
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


def tool_messages(run: TaskRun) -> list[dict]:
    assert run.trace is not None
    return [dict(m) for m in run.trace if m["role"] == "tool"]


def assert_usage(
    usage: MessageUsage | None,
    *,
    cost: float | None,
    input_tokens: int,
    output_tokens: int,
) -> None:
    assert usage is not None
    assert usage.cost == (None if cost is None else pytest.approx(cost))
    assert usage.input_tokens == input_tokens
    assert usage.output_tokens == output_tokens
    assert usage.total_tokens == input_tokens + output_tokens


async def test_interactive_run_includes_its_sub_agent_call(agents, provider):
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"),), cost=0.001, input_tokens=100, output_tokens=10
        ),
        reply("done", cost=0.002, input_tokens=120, output_tokens=5),
    )
    provider.script(
        child, reply("child answer", cost=0.01, input_tokens=1000, output_tokens=50)
    )

    run = await agents.adapter(parent).invoke("go")

    total = {"cost": 0.013, "input_tokens": 1220, "output_tokens": 65}
    assert_usage(run.usage, **total)
    assert_usage(run.cumulative_usage, **total)

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

    # Latency stays the parent's own model calls: tool time is not LLM wait time.
    assert run.usage.total_llm_latency_ms == sum(
        m["latency_ms"] for m in run.trace if m["role"] == "assistant"
    )

    # The saved file keeps the per-message usage, so the total can be re-derived.
    assert run.path is not None
    reloaded = TaskRun.load_from_file(run.path)
    assert_usage(reloaded.usage, **total)
    assert_usage(MessageUsage.from_trace(reloaded.trace), **total)


async def test_each_call_is_counted_once_when_a_tool_is_called_several_times(
    agents, provider
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

    run = await agents.adapter(parent).invoke("go")

    assert sorted(m["usage"].cost for m in tool_messages(run)) == [0.01, 0.02, 0.04]
    total = {"cost": 0.077, "input_tokens": 7700, "output_tokens": 77}
    assert_usage(run.usage, **total)
    assert_usage(run.cumulative_usage, **total)
    assert len(child.runs()) == 3


async def test_nested_sub_agents_are_counted_once(agents, provider):
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
        ),
        reply("child answer", cost=0.02, input_tokens=2000, output_tokens=20),
    )
    provider.script(
        grandchild,
        reply("grandchild answer", cost=0.1, input_tokens=10000, output_tokens=100),
    )

    run = await agents.adapter(parent).invoke("go")

    grandchild_total = {"cost": 0.1, "input_tokens": 10000, "output_tokens": 100}
    child_total = {"cost": 0.13, "input_tokens": 13000, "output_tokens": 130}
    parent_total = {"cost": 0.133, "input_tokens": 13300, "output_tokens": 133}

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


@pytest.mark.parametrize(
    "parent_cost, child_cost, expected_cost",
    [
        pytest.param(0.001, None, 0.002, id="sub_agent_cost_unknown"),
        pytest.param(None, 0.01, 0.01, id="parent_cost_unknown"),
        pytest.param(None, None, None, id="all_costs_unknown"),
    ],
)
async def test_unknown_cost_is_left_out_of_the_sum_not_counted_as_zero(
    agents, provider, parent_cost, child_cost, expected_cost
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

    run = await agents.adapter(parent).invoke("go")

    total = {"cost": expected_cost, "input_tokens": 1220, "output_tokens": 65}
    assert_usage(run.usage, **total)
    assert_usage(run.cumulative_usage, **total)


async def test_streamed_run_includes_its_sub_agent_call(agents, provider):
    child = agents.add("child")
    parent = agents.add("parent", sub_agents=(child,))
    provider.script(
        parent,
        reply(
            calls=(("c1", "ask_child"),), cost=0.001, input_tokens=100, output_tokens=10
        ),
        reply("done", cost=0.002, input_tokens=120, output_tokens=5),
    )
    provider.script(
        child, reply("child answer", cost=0.01, input_tokens=1000, output_tokens=50)
    )

    stream = agents.adapter(parent).invoke_openai_stream("go")
    async for _ in stream:
        pass

    total = {"cost": 0.013, "input_tokens": 1220, "output_tokens": 65}
    assert_usage(stream.task_run.usage, **total)
    assert_usage(stream.task_run.cumulative_usage, **total)


async def test_continued_conversation_keeps_earlier_sub_agent_calls_in_cumulative_usage(
    agents, provider
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

    first = await agents.adapter(parent).invoke("go")
    second = await agents.adapter(parent).invoke("go on", prior_trace=first.trace)

    # `usage` is this turn only; `cumulative_usage` is the whole conversation.
    assert_usage(second.usage, cost=0.032, input_tokens=3200, output_tokens=32)
    assert_usage(
        second.cumulative_usage, cost=0.045, input_tokens=4500, output_tokens=45
    )


async def test_eval_job_run_includes_a_sub_agent_whose_run_is_not_saved(
    agents, provider
):
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
        child, reply("child answer", cost=0.01, input_tokens=1000, output_tokens=50)
    )

    eval = Eval(
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
    eval.save_to_file()
    eval_config = EvalConfig(
        parent=eval,
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
    split = resolve_split(parent, eval, "test")
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
    total = {"cost": 0.013, "input_tokens": 1220, "output_tokens": 65}
    assert_usage(scored_run.usage, **total)
    assert_usage(scored_run.cumulative_usage, **total)

    # An eval job saves no run for the sub-agent, so the parent's trace is the
    # only record of what the sub-agent spent.
    assert child.runs() == []
    (tool_message,) = tool_messages(scored_run)
    assert tool_message["kiln_task_tool_data"].endswith(":::None")
    assert_usage(tool_message["usage"], cost=0.01, input_tokens=1000, output_tokens=50)
