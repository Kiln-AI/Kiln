"""Tests for the OpenEnv session behind one adapter run, against the in-process test
environment server. The adapter tests run the real `LiteLlmAdapter`, stubbed only at the
model provider call."""

import asyncio
import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from litellm.types.utils import ModelResponse

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.ml_model_list import KilnModelProvider
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter
from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
    TurnMode,
)
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    MCPToolReference,
    ToolsRunConfig,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_output import TaskOutput
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.datamodel.tool_id import build_openenv_tool_id
from kiln_ai.openenv.run_session import (
    OpenEnvRunError,
    openenv_for_run,
)
from kiln_ai.openenv.session_manager import (
    OpenEnvRejectedError,
    OpenEnvSessionManager,
    OpenEnvTransientError,
)
from kiln_ai.openenv.testing import free_port, serve_in_thread
from kiln_ai.run_context import (
    EpisodeContext,
    get_episode,
    no_openenv_sessions,
    reset_episode,
    set_episode,
)
from kiln_ai.tools.tool_registry import tool_from_id


@pytest.fixture
def project(tmp_path):
    p = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    p.path.parent.mkdir(parents=True)
    p.save_to_file()
    return p


@pytest.fixture
def task(project):
    t = Task(name="task", instruction="write a note", parent=project)
    t.save_to_file()
    return t


@pytest.fixture
def openenv_server_url():
    with serve_in_thread() as base_url:
        yield base_url


def _openenv_server(project, url, name="Acme"):
    openenv_server = OpenEnvServer(name=name, parent=project, url=url)
    openenv_server.save_to_file()
    return openenv_server


@pytest.fixture
def openenv_server(project, openenv_server_url):
    return _openenv_server(project, openenv_server_url)


@pytest.fixture
async def session_manager():
    session_manager = OpenEnvSessionManager()
    try:
        yield session_manager
    finally:
        await session_manager.shutdown()


def _properties(tool_ids):
    return KilnAgentRunConfigProperties(
        model_name="gpt-4",
        model_provider_name="openai",
        prompt_id="simple_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
        tools_config=ToolsRunConfig(tools=tool_ids),
    )


def _openenv_server_properties(openenv_server, tool_name="append_note"):
    return _properties([build_openenv_tool_id(openenv_server.id, tool_name)])


async def _enter(task, properties, session_manager, reset_kwargs=None):
    async with openenv_for_run(
        task, properties, reset_kwargs, session_manager=session_manager
    ) as handle:
        return handle


class TestNoOpenEnvServer:
    @pytest.mark.parametrize("tool_ids", [[], ["kiln_tool::add_numbers"]])
    async def test_yields_none_and_opens_nothing(self, task, session_manager, tool_ids):
        assert await _enter(task, _properties(tool_ids), session_manager) is None
        assert session_manager._sessions == {}

    async def test_mcp_run_config_has_no_openenv_server(self, task, session_manager):
        properties = McpRunConfigProperties(
            tool_reference=MCPToolReference(tool_id="mcp::remote::s::t")
        )
        assert await _enter(task, properties, session_manager) is None

    async def test_reset_kwargs_need_an_openenv_server(self, task, session_manager):
        with pytest.raises(OpenEnvRunError) as raised:
            await _enter(task, _properties([]), session_manager, {"role": "tech"})
        assert raised.value.kind == "kwargs_without_openenv"
        assert "don't use an OpenEnv server" in raised.value.message

    async def test_sessions_off_opens_nothing(
        self, task, openenv_server, session_manager
    ):
        with no_openenv_sessions():
            handle = await _enter(
                task, _openenv_server_properties(openenv_server), session_manager
            )
        assert handle is None
        assert session_manager._servers == {}

    def test_reset_kwargs_need_open_openenv_session(self):
        with pytest.raises(ValueError, match="need open_openenv_session"):
            AdapterConfig(open_openenv_session=False, openenv_reset_kwargs={})

    async def test_active_episode_is_reused(
        self, task, openenv_server, session_manager
    ):
        """A Kiln task tool's sub-run, or a run inside an eval job, uses the episode
        already set rather than opening another."""
        episode = await session_manager.start_episode(openenv_server, {})
        token = set_episode(
            EpisodeContext(
                episode=episode,
                openenv_server=openenv_server,
                session_manager=session_manager,
            )
        )
        try:
            handle = await _enter(
                task, _openenv_server_properties(openenv_server), session_manager
            )
            assert handle is None
            assert list(session_manager._sessions) == [episode.episode_id]
        finally:
            reset_episode(token)
            await session_manager.release(episode)


class TestSetupErrors:
    async def test_two_openenv_servers(
        self, project, task, openenv_server_url, session_manager
    ):
        acme = _openenv_server(project, openenv_server_url, "Acme")
        beta = _openenv_server(project, openenv_server_url, "Beta")
        properties = _properties(
            [
                build_openenv_tool_id(acme.id, "append_note"),
                build_openenv_tool_id(beta.id, "read_notes"),
            ]
        )
        with pytest.raises(OpenEnvRunError) as raised:
            await _enter(task, properties, session_manager)
        assert raised.value.kind == "reach"
        assert raised.value.message == (
            "Your tools use more than one OpenEnv server (Acme, Beta). A run can only use one."
        )

    async def test_missing_openenv_server(self, task, session_manager):
        properties = _properties([build_openenv_tool_id("gone", "append_note")])
        with pytest.raises(OpenEnvRunError) as raised:
            await _enter(task, properties, session_manager)
        assert raised.value.kind == "not_found"
        assert raised.value.message == "OpenEnv server gone wasn't found."

    async def test_unreachable(self, project, task, session_manager):
        url = f"http://127.0.0.1:{free_port()}"
        openenv_server = _openenv_server(project, url)
        with pytest.raises(OpenEnvRunError) as raised:
            await _enter(
                task, _openenv_server_properties(openenv_server), session_manager
            )
        assert raised.value.kind == "unreachable"
        assert raised.value.message == (
            f"Can't reach OpenEnv server Acme at {url}. Check the server is running."
        )

    async def test_at_capacity(self, project, task, session_manager):
        with serve_in_thread(max_sessions=1) as url:
            openenv_server = _openenv_server(project, url)
            held = await session_manager.start_episode(openenv_server, {})
            with pytest.raises(OpenEnvRunError) as raised:
                await _enter(
                    task, _openenv_server_properties(openenv_server), session_manager
                )
            await session_manager.release(held)
        assert raised.value.kind == "at_capacity"
        assert raised.value.message == (
            "OpenEnv server Acme is at capacity. Wait for a run to finish, or raise the "
            "server's session limit."
        )

    async def test_reset_rejected(self, task, openenv_server, session_manager):
        with pytest.raises(OpenEnvRunError) as raised:
            await _enter(
                task,
                _openenv_server_properties(openenv_server),
                session_manager,
                {"fail_reset": True},
            )
        assert raised.value.kind == "reset_rejected"
        assert raised.value.message == (
            "Acme rejected the reset arguments: reset refused"
        )
        assert session_manager._sessions == {}

    async def test_rejected_tool_listing_is_unreachable_not_a_reset_error(
        self, task, openenv_server, session_manager
    ):
        with patch.object(
            session_manager, "list_tools", side_effect=OpenEnvRejectedError("no")
        ):
            with pytest.raises(OpenEnvRunError) as raised:
                await _enter(
                    task, _openenv_server_properties(openenv_server), session_manager
                )
        assert raised.value.kind == "unreachable"


class TestSession:
    async def test_runs_in_the_episode_and_records_final_state(
        self, task, openenv_server, session_manager
    ):
        properties = _openenv_server_properties(openenv_server)
        async with openenv_for_run(
            task, properties, {"fixture_id": "acme"}, session_manager=session_manager
        ) as handle:
            assert handle is not None
            assert get_episode() is handle.context
            tool = tool_from_id(
                build_openenv_tool_id(openenv_server.id, "append_note"), task
            )
            await tool.run(note="hi")
            assert handle.episode is None

        assert get_episode() is None
        assert session_manager._sessions == {}
        episode = handle.episode
        assert episode is not None
        assert episode.reset.openenv_server_id == openenv_server.id
        assert episode.reset.reset_kwargs == {"fixture_id": "acme"}
        assert episode.final_state is not None
        assert episode.final_state["notes"] == ["hi"]

    async def test_no_reset_kwargs_resets_with_none(
        self, task, openenv_server, session_manager
    ):
        handle = await _enter(
            task, _openenv_server_properties(openenv_server), session_manager
        )
        assert handle is not None and handle.episode is not None
        assert handle.episode.reset.reset_kwargs == {}

    async def test_error_releases_the_session(
        self, task, openenv_server, session_manager
    ):
        with pytest.raises(RuntimeError, match="model failed"):
            async with openenv_for_run(
                task,
                _openenv_server_properties(openenv_server),
                None,
                session_manager=session_manager,
            ) as handle:
                assert handle is not None
                raise RuntimeError("model failed")
        assert handle.episode is None
        assert get_episode() is None
        assert session_manager._sessions == {}

    async def test_unreadable_final_state_keeps_the_episode(
        self, task, openenv_server, session_manager
    ):
        handle = await _enter(
            task,
            _openenv_server_properties(openenv_server),
            session_manager,
            {"fail_state": True},
        )
        assert handle is not None and handle.episode is not None
        assert handle.episode.final_state is None
        assert session_manager._sessions == {}


def _model_reply(content=None, note=None):
    tool_calls = (
        [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "append_note",
                    "arguments": json.dumps({"note": note}),
                },
            }
        ]
        if note is not None
        else None
    )
    response = ModelResponse(
        model="gpt-4",
        choices=[{"message": {"content": content, "tool_calls": tool_calls}}],
    )
    return response, response.choices[0]


@contextmanager
def _stubbed_model(session_manager, *replies):
    provider = KilnModelProvider(name=ModelProviderName.openai, model_id="gpt-4")
    with (
        patch(
            "kiln_ai.adapters.adapter_registry.kiln_model_provider_from",
            return_value=provider,
        ),
        patch(
            "kiln_ai.openenv.run_session.shared_session_manager",
            return_value=session_manager,
        ),
        patch(
            "kiln_ai.openenv.run_session.shared_conversation_sessions",
            return_value=session_manager.conversations,
        ),
        patch.object(LiteLlmAdapter, "model_provider", return_value=provider),
        patch.object(LiteLlmAdapter, "build_completion_kwargs", return_value={}),
        patch.object(
            LiteLlmAdapter, "acompletion_checking_response", side_effect=list(replies)
        ) as model_call,
    ):
        yield model_call


class TestAdapterRun:
    @pytest.mark.parametrize("allow_saving", [True, False])
    async def test_run_records_the_episode(
        self, task, openenv_server, session_manager, allow_saving
    ):
        with _stubbed_model(
            session_manager, _model_reply(note="hi"), _model_reply(content="done")
        ):
            adapter = adapter_for_task(
                task,
                _openenv_server_properties(openenv_server),
                AdapterConfig(
                    allow_saving=allow_saving,
                    openenv_reset_kwargs={"fixture_id": "acme"},
                ),
            )
            run = await adapter.invoke("write hi")

        assert run.output.output == "done"
        assert run.openenv_episode is not None
        assert run.openenv_episode.reset.reset_kwargs == {"fixture_id": "acme"}
        assert run.openenv_episode.final_state is not None
        assert run.openenv_episode.final_state["notes"] == ["hi"]
        assert session_manager._sessions == {}
        if allow_saving:
            assert run.id is not None
            saved = TaskRun.from_id_and_parent_path(run.id, task.path)
            assert saved is not None and saved.openenv_episode == run.openenv_episode
        else:
            assert run.path is None

    async def test_setup_error_is_raised_before_the_model_is_called(
        self, task, session_manager
    ):
        with _stubbed_model(session_manager) as model_call:
            adapter = adapter_for_task(
                task, _properties([build_openenv_tool_id("gone", "append_note")])
            )
            with pytest.raises(OpenEnvRunError) as raised:
                await adapter.invoke("write hi")
        assert not isinstance(raised.value, KilnRunError)
        assert raised.value.kind == "not_found"
        assert model_call.call_count == 0

    async def test_run_without_an_openenv_server_records_no_episode(
        self, task, session_manager
    ):
        with _stubbed_model(session_manager, _model_reply(content="done")):
            adapter = adapter_for_task(task, _properties([]))
            run = await adapter.invoke("hello")
        assert run.openenv_episode is None

    async def test_opted_out_run_opens_no_session(
        self, task, openenv_server, session_manager
    ):
        with _stubbed_model(session_manager, _model_reply(content="done")):
            adapter = adapter_for_task(
                task,
                _openenv_server_properties(openenv_server),
                AdapterConfig(open_openenv_session=False),
            )
            run = await adapter.invoke("hello")
        assert run.openenv_episode is None
        assert session_manager._servers == {}


class TestStreaming:
    @pytest.mark.parametrize("stream", ["invoke_openai_stream", "invoke_ai_sdk_stream"])
    @pytest.mark.parametrize("reaches_openenv_server", [True, False])
    async def test_stream_needing_a_session_is_refused(
        self, task, openenv_server, session_manager, stream, reaches_openenv_server
    ):
        properties, config = (
            (_openenv_server_properties(openenv_server), AdapterConfig())
            if reaches_openenv_server
            else (_properties([]), AdapterConfig(openenv_reset_kwargs={"role": "tech"}))
        )
        with _stubbed_model(session_manager) as model_call:
            adapter = adapter_for_task(task, properties, config)
            with pytest.raises(
                ValueError, match="Streaming runs can't use an OpenEnv server"
            ):
                async for _ in getattr(adapter, stream)("hello"):
                    pass
        assert model_call.call_count == 0

    async def test_stream_reaching_two_openenv_servers_is_a_value_error(
        self, project, task, openenv_server_url, session_manager
    ):
        acme = _openenv_server(project, openenv_server_url, "Acme")
        beta = _openenv_server(project, openenv_server_url, "Beta")
        properties = _properties(
            [
                build_openenv_tool_id(acme.id, "append_note"),
                build_openenv_tool_id(beta.id, "read_notes"),
            ]
        )
        with _stubbed_model(session_manager):
            adapter = adapter_for_task(task, properties)
            with pytest.raises(ValueError, match="more than one OpenEnv server"):
                adapter._prepare_stream("hello", None)

    async def test_stream_where_sessions_are_off_is_allowed(
        self, task, openenv_server, session_manager
    ):
        with _stubbed_model(session_manager), no_openenv_sessions():
            adapter = adapter_for_task(task, _openenv_server_properties(openenv_server))
            assert adapter._prepare_stream("hello", None) is not None

    async def test_stream_inside_an_episode_is_allowed(
        self, task, openenv_server, session_manager
    ):
        episode = await session_manager.start_episode(openenv_server, {})
        token = set_episode(
            EpisodeContext(
                episode=episode,
                openenv_server=openenv_server,
                session_manager=session_manager,
            )
        )
        try:
            with _stubbed_model(session_manager):
                adapter = adapter_for_task(
                    task, _openenv_server_properties(openenv_server)
                )
                assert adapter._prepare_stream("hello", None) is not None
        finally:
            reset_episode(token)
            await session_manager.release(episode)


@pytest.fixture
def multiturn_task(project):
    t = Task(
        name="chat",
        instruction="keep notes",
        parent=project,
        turn_mode=TurnMode.multiturn,
    )
    t.save_to_file()
    return t


def _conversation_turn(task, properties, session_manager, parent, reset_kwargs=None):
    return openenv_for_run(
        task,
        properties,
        reset_kwargs,
        parent,
        session_manager,
        session_manager.conversations,
    )


async def _turn(
    task, properties, session_manager, parent=None, reset_kwargs=None, note=None
):
    """One conversation turn: optionally append a note through the environment's tool,
    then record the turn as a run the way the adapter does."""
    async with _conversation_turn(
        task, properties, session_manager, parent, reset_kwargs
    ) as handle:
        assert handle is not None
        if note is not None:
            tool = tool_from_id(properties.tools_config.tools[0], task)
            await tool.run(note=note)
        run = TaskRun(
            input="hi",
            output=TaskOutput(output="ok"),
            parent=task,
            parent_task_run_id=parent.id if parent else None,
        )
        handle.run_id = run.id
    run.openenv_episode = handle.episode
    return run


class TestConversation:
    async def test_turns_share_one_session_and_record_their_state(
        self, multiturn_task, openenv_server, session_manager
    ):
        properties = _openenv_server_properties(openenv_server)
        first = await _turn(
            multiturn_task,
            properties,
            session_manager,
            reset_kwargs={"fixture_id": "acme"},
            note="one",
        )
        second = await _turn(
            multiturn_task,
            properties,
            session_manager,
            parent=first,
            reset_kwargs={"fixture_id": "beta"},
            note="two",
        )

        assert first.openenv_episode is not None and second.openenv_episode is not None
        assert first.openenv_episode.episode_id == second.openenv_episode.episode_id
        assert first.openenv_episode.final_state is not None
        assert first.openenv_episode.final_state["notes"] == ["one"]
        assert second.openenv_episode.final_state is not None
        assert second.openenv_episode.final_state["notes"] == ["one", "two"]
        # Later turns ignore reset kwargs: the first turn fixed them.
        assert second.openenv_episode.reset.reset_kwargs == {"fixture_id": "acme"}
        assert second.openenv_episode.final_state["fixture_id"] == "acme"
        assert get_episode() is None
        assert list(session_manager._sessions) == [second.openenv_episode.episode_id]
        assert session_manager.conversations.take(str(second.id)) is not None

    async def test_continuing_an_earlier_turn_is_refused(
        self, multiturn_task, openenv_server, session_manager
    ):
        properties = _openenv_server_properties(openenv_server)
        first = await _turn(multiturn_task, properties, session_manager)
        await _turn(multiturn_task, properties, session_manager, parent=first)
        with pytest.raises(OpenEnvRunError) as raised:
            await _turn(multiturn_task, properties, session_manager, parent=first)
        assert raised.value.kind == "fork_refused"
        assert raised.value.message == (
            "This conversation uses an OpenEnv server, so it can only continue from the "
            "latest turn."
        )

    async def test_ended_session_is_refused(
        self, multiturn_task, openenv_server, session_manager
    ):
        properties = _openenv_server_properties(openenv_server)
        first = await _turn(multiturn_task, properties, session_manager)
        await session_manager.conversations.release_runs([str(first.id)])
        with pytest.raises(OpenEnvRunError) as raised:
            await _turn(multiturn_task, properties, session_manager, parent=first)
        assert raised.value.kind == "session_ended"
        assert raised.value.message == (
            "The OpenEnv session for this conversation ended. Start a new "
            "conversation to keep using this OpenEnv server."
        )
        assert session_manager._sessions == {}

    async def test_conversation_started_without_an_openenv_server_is_refused(
        self, multiturn_task, openenv_server, session_manager
    ):
        parent = TaskRun(
            input="hi", output=TaskOutput(output="ok"), parent=multiturn_task
        )
        with pytest.raises(OpenEnvRunError) as raised:
            await _turn(
                multiturn_task,
                _openenv_server_properties(openenv_server),
                session_manager,
                parent=parent,
            )
        assert raised.value.kind == "not_started_with_openenv"
        assert raised.value.message == (
            "This conversation started without an OpenEnv server. Start a new conversation "
            "to use one."
        )
        assert session_manager._sessions == {}

    @pytest.mark.parametrize(
        "other, expected",
        [
            ("Beta", "Start a new conversation to use Beta."),
            (None, "Start a new conversation to run without it."),
        ],
    )
    async def test_changing_openenv_server_is_refused_and_keeps_the_session(
        self,
        project,
        multiturn_task,
        openenv_server_url,
        openenv_server,
        session_manager,
        other,
        expected,
    ):
        first = await _turn(
            multiturn_task, _openenv_server_properties(openenv_server), session_manager
        )
        properties = (
            _openenv_server_properties(
                _openenv_server(project, openenv_server_url, other)
            )
            if other
            else _properties([])
        )
        with pytest.raises(OpenEnvRunError) as raised:
            await _turn(multiturn_task, properties, session_manager, parent=first)
        assert raised.value.kind == "openenv_changed"
        assert (
            raised.value.message
            == f"This conversation uses OpenEnv server Acme. {expected}"
        )
        assert session_manager.conversations.holds_turn(str(first.id))
        second = await _turn(
            multiturn_task,
            _openenv_server_properties(openenv_server),
            session_manager,
            parent=first,
        )
        assert second.openenv_episode is not None and first.openenv_episode is not None
        assert second.openenv_episode.episode_id == first.openenv_episode.episode_id

    async def test_failed_turn_can_be_retried(
        self, multiturn_task, openenv_server, session_manager
    ):
        properties = _openenv_server_properties(openenv_server)
        first = await _turn(multiturn_task, properties, session_manager, note="one")
        with pytest.raises(KilnRunError):
            async with _conversation_turn(
                multiturn_task, properties, session_manager, first
            ):
                raise KilnRunError(
                    "rate limited", partial_trace=None, original=RuntimeError("429")
                )
        retried = await _turn(
            multiturn_task, properties, session_manager, parent=first, note="two"
        )
        assert retried.openenv_episode is not None
        assert retried.openenv_episode.final_state is not None
        assert retried.openenv_episode.final_state["notes"] == ["one", "two"]

    async def test_turn_that_ends_the_session_releases_it(
        self, multiturn_task, openenv_server, session_manager
    ):
        properties = _openenv_server_properties(openenv_server)
        first = await _turn(multiturn_task, properties, session_manager)
        with pytest.raises(KilnRunError):
            async with _conversation_turn(
                multiturn_task, properties, session_manager, first
            ):
                raise KilnRunError(
                    "env dropped",
                    partial_trace=None,
                    original=OpenEnvTransientError("closed"),
                )
        assert session_manager._sessions == {}
        with pytest.raises(OpenEnvRunError) as raised:
            await _turn(multiturn_task, properties, session_manager, parent=first)
        assert raised.value.kind == "session_ended"

    async def test_failed_first_turn_releases_the_session(
        self, multiturn_task, openenv_server, session_manager
    ):
        with pytest.raises(RuntimeError, match="model failed"):
            async with _conversation_turn(
                multiturn_task,
                _openenv_server_properties(openenv_server),
                session_manager,
                None,
            ):
                raise RuntimeError("model failed")
        assert session_manager._sessions == {}

    async def test_rejected_state_keeps_the_session(
        self, multiturn_task, openenv_server, session_manager
    ):
        first = await _turn(
            multiturn_task,
            _openenv_server_properties(openenv_server),
            session_manager,
            reset_kwargs={"fail_state": True},
        )
        assert first.openenv_episode is not None
        assert first.openenv_episode.final_state is None
        assert session_manager.conversations.holds_turn(str(first.id))

    async def test_state_lost_with_the_session_ends_the_conversation(
        self, multiturn_task, openenv_server, session_manager
    ):
        with patch.object(
            session_manager, "read_state", side_effect=OpenEnvTransientError("closed")
        ):
            first = await _turn(
                multiturn_task,
                _openenv_server_properties(openenv_server),
                session_manager,
            )
        assert first.openenv_episode is not None
        assert first.openenv_episode.final_state is None
        assert session_manager._sessions == {}
        assert not session_manager.conversations.holds_turn(str(first.id))

    async def test_turn_without_a_run_id_releases_the_session(
        self, multiturn_task, openenv_server, session_manager
    ):
        async with _conversation_turn(
            multiturn_task,
            _openenv_server_properties(openenv_server),
            session_manager,
            None,
        ) as handle:
            assert handle is not None
        assert handle.episode is not None
        assert session_manager._sessions == {}

    async def test_turn_without_an_openenv_server_is_unchanged(
        self, multiturn_task, session_manager
    ):
        async with _conversation_turn(
            multiturn_task, _properties([]), session_manager, None
        ) as handle:
            assert handle is None


class TestAdapterConversation:
    async def test_three_turns_share_one_episode(
        self, multiturn_task, openenv_server, session_manager
    ):
        replies = []
        for note in ("one", "two", "three"):
            replies += [_model_reply(note=note), _model_reply(content=f"noted {note}")]
        runs: list[TaskRun] = []
        with _stubbed_model(session_manager, *replies):
            for i in range(3):
                adapter = adapter_for_task(
                    multiturn_task,
                    _openenv_server_properties(openenv_server),
                    AdapterConfig(openenv_reset_kwargs={"fixture_id": "acme"}),
                )
                parent = runs[-1] if runs else None
                runs.append(
                    await adapter.invoke(
                        f"turn {i}",
                        prior_trace=parent.trace if parent else None,
                        parent_task_run=parent,
                    )
                )

        episodes = [run.openenv_episode for run in runs]
        assert len({e.episode_id for e in episodes if e}) == 1
        assert [e.final_state["notes"] for e in episodes if e and e.final_state] == [
            ["one"],
            ["one", "two"],
            ["one", "two", "three"],
        ]
        for run in runs:
            assert run.id is not None
            saved = TaskRun.from_id_and_parent_path(run.id, multiturn_task.path)
            assert saved is not None and saved.openenv_episode == run.openenv_episode
        assert session_manager.conversations.holds_turn(str(runs[-1].id))


def _openenv_adapter(task, openenv_server):
    return adapter_for_task(
        task, _openenv_server_properties(openenv_server), AdapterConfig()
    )


class TestLostConversationSession:
    """A session lost during or between turns fails the turn that finds it gone."""

    async def test_cancelled_turn_releases_the_session(
        self, multiturn_task, openenv_server, session_manager
    ):
        properties = _openenv_server_properties(openenv_server)
        first = await _turn(multiturn_task, properties, session_manager)
        with pytest.raises(asyncio.CancelledError):
            async with _conversation_turn(
                multiturn_task, properties, session_manager, first
            ):
                raise asyncio.CancelledError()
        assert session_manager._sessions == {}
        assert not session_manager.conversations.holds_turn(str(first.id))

    async def test_tool_error_that_drops_the_session_fails_the_turn(
        self, multiturn_task, openenv_server, session_manager
    ):
        with _stubbed_model(
            session_manager, _model_reply(content="hi"), _model_reply(note="two")
        ):
            first = await _openenv_adapter(multiturn_task, openenv_server).invoke(
                "turn 0"
            )
            with patch.object(
                session_manager,
                "_request",
                side_effect=RuntimeError("attached to a different loop"),
            ):
                with pytest.raises(KilnRunError):
                    await _openenv_adapter(multiturn_task, openenv_server).invoke(
                        "turn 1", prior_trace=first.trace, parent_task_run=first
                    )
            assert session_manager._sessions == {}
            with pytest.raises(OpenEnvRunError) as raised:
                await _openenv_adapter(multiturn_task, openenv_server).invoke(
                    "turn 1 again", prior_trace=first.trace, parent_task_run=first
                )
        assert raised.value.kind == "session_ended"

    @pytest.mark.parametrize("switch_openenv_server", [False, True])
    def test_turn_on_another_event_loop_is_refused(
        self,
        project,
        multiturn_task,
        openenv_server_url,
        openenv_server,
        switch_openenv_server,
    ):
        """A library caller running each turn in its own `asyncio.run` can't reuse a
        socket opened on the previous loop, whatever the later turn's tools reach."""
        session_manager = OpenEnvSessionManager()
        second_openenv_server = (
            _openenv_server(project, openenv_server_url, "Beta")
            if switch_openenv_server
            else openenv_server
        )
        with _stubbed_model(session_manager, _model_reply(content="hi")) as model_call:
            first = asyncio.run(
                _openenv_adapter(multiturn_task, openenv_server).invoke("turn 0")
            )
            with pytest.raises(OpenEnvRunError) as raised:
                asyncio.run(
                    _openenv_adapter(multiturn_task, second_openenv_server).invoke(
                        "turn 1", prior_trace=first.trace, parent_task_run=first
                    )
                )
        assert raised.value.kind == "session_ended"
        assert model_call.call_count == 1
        assert first.openenv_episode is not None
        assert first.openenv_episode.episode_id not in session_manager._sessions
