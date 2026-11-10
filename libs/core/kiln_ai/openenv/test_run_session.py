"""Tests for the OpenEnv session behind one adapter run, against the in-process test
environment server. The adapter tests run the real `LiteLlmAdapter`, stubbed only at the
model provider call."""

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
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.openenv import OpenEnvServer
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    MCPToolReference,
    ToolsRunConfig,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.datamodel.tool_id import build_openenv_tool_id
from kiln_ai.openenv.run_session import (
    OpenEnvRunError,
    openenv_for_run,
)
from kiln_ai.openenv.session_manager import (
    OpenEnvRejectedError,
    OpenEnvSessionManager,
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
        task, properties, reset_kwargs, session_manager
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
        assert "don't use an OpenEnv" in raised.value.message

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
        assert raised.value.message == "OpenEnv gone wasn't found."

    async def test_unreachable(self, project, task, session_manager):
        url = f"http://127.0.0.1:{free_port()}"
        openenv_server = _openenv_server(project, url)
        with pytest.raises(OpenEnvRunError) as raised:
            await _enter(
                task, _openenv_server_properties(openenv_server), session_manager
            )
        assert raised.value.kind == "unreachable"
        assert raised.value.message == (
            f"Can't reach OpenEnv Acme at {url}. Check the server is running."
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
            "OpenEnv Acme is at capacity. Wait for a run to finish, or raise the "
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
            task, properties, {"fixture_id": "acme"}, session_manager
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
                task, _openenv_server_properties(openenv_server), None, session_manager
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
            with pytest.raises(ValueError, match="Streaming runs can't use an OpenEnv"):
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
