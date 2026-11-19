import asyncio
import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, TurnMode
from kiln_ai.datamodel.openenv import OpenEnvReset, OpenEnvServer
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties, ToolsRunConfig
from kiln_ai.datamodel.tool_id import build_openenv_tool_id
from kiln_ai.eval_grounding.batch import (
    CaseGrounded,
    GroundingCaseError,
    GroundingFinished,
)
from kiln_ai.eval_grounding.models import (
    DropReason,
    Evidence,
    Fact,
    GroundedReference,
    GroundingOutcome,
)
from kiln_ai.openenv.session_manager import OpenEnvError, OpenEnvSessionManager
from kiln_ai.openenv.testing import serve_in_thread
from kiln_ai.utils.usage import Usage
from kiln_server.custom_errors import connect_custom_errors

from app.desktop.studio_server.api_models.eval_builder_models import (
    GroundCaseApi,
    GroundingModelApi,
)
from app.desktop.studio_server.eval_builder_api import (
    _grounding_sse,
    connect_eval_builder_api,
)
from app.desktop.studio_server.services.eval_grounding import grounding_frames

GROUND_URL = "/api/projects/p1/tasks/t1/eval_builder/ground_cases"
API = "app.desktop.studio_server.eval_builder_api"
SERVICE = "app.desktop.studio_server.services.eval_grounding"

USER_INFO = "<persona>A support lead.</persona><goal>Close ticket 7.</goal>"


@pytest.fixture
def server_url():
    """Holds one session, so an episode left open blocks the next one."""
    with serve_in_thread(max_sessions=1) as base_url:
        yield base_url


@pytest.fixture
def project_task_server(tmp_path, server_url):
    project = Project(name="proj", path=tmp_path / "proj" / "project.kiln")
    project.path.parent.mkdir(parents=True)
    project.save_to_file()
    task = Task(
        name="support",
        instruction="You help with tickets.",
        turn_mode=TurnMode.multiturn,
        parent=project,
    )
    task.save_to_file()
    server = OpenEnvServer(name="counter", url=server_url, parent=project)
    server.save_to_file()
    return project, task, server


@pytest.fixture
async def session_manager():
    manager = OpenEnvSessionManager()
    try:
        yield manager
    finally:
        await manager.shutdown()


@pytest.fixture
def client(project_task_server, session_manager):
    project, task, _server = project_task_server
    app = FastAPI()
    connect_custom_errors(app)
    connect_eval_builder_api(app)
    with (
        patch(f"{API}.project_from_id", return_value=project),
        patch(f"{API}.task_from_id", return_value=task),
        patch(f"{API}.shared_session_manager", return_value=session_manager),
    ):
        yield TestClient(app)


def _run_config(tool_ids: list[str]) -> KilnAgentRunConfigProperties:
    return KilnAgentRunConfigProperties(
        model_name="gpt_5_5",
        model_provider_name=ModelProviderName.openrouter,
        prompt_id=PromptGenerators.SIMPLE,
        structured_output_mode="default",
        tools_config=ToolsRunConfig(tools=tool_ids),
    )


def _case(i: int) -> dict[str, Any]:
    return {
        "scenario_index": i + 3,
        "scenario": f"scenario {i}",
        "seed_prompt": f"seed {i}",
        "synthetic_user_info": USER_INFO,
    }


def _request(server: OpenEnvServer, **overrides: Any) -> dict[str, Any]:
    return {
        "target_run_config": _run_config(
            [build_openenv_tool_id(server.id, "read_notes")]
        ).model_dump(mode="json"),
        "judge_model": {"model_name": "claude_opus_4_5", "model_provider": "anthropic"},
        "specification": "The agent closes the right ticket.",
        "synthetic_user_guide": "Support leads triaging tickets.",
        "cases": [_case(0), _case(1)],
        **overrides,
    }


def _reference() -> GroundedReference:
    return GroundedReference(
        starting_point="Ticket 7 is open.",
        facts=[
            Fact(
                text="Ticket 7 exists.",
                evidence=Evidence(
                    tool="read_notes", args={"id": 7}, result_excerpt="ticket 7"
                ),
            )
        ],
        expected_outcome=["Ticket 7 is closed."],
        allowed=[],
        must_not_happen=["Ticket 8 is closed."],
    )


def _grounded(server: OpenEnvServer) -> GroundingOutcome:
    return GroundingOutcome(
        status="grounded",
        openenv_reset=OpenEnvReset(
            openenv_server_id=str(server.id), reset_kwargs={"fixture_id": "f1"}
        ),
        seed_prompt="Close ticket 7 please.",
        synthetic_user_info=USER_INFO,
        reference=_reference(),
    )


def _dropped() -> GroundingOutcome:
    return GroundingOutcome.dropped(
        DropReason.no_fit,
        "No ticket is assigned to a support lead.",
        call_log=[],
        usage=None,
    )


def _fake_ground_cases(items: list[Any], calls: list[dict[str, Any]]):
    """Yields `items` in order; an exception in the list is raised in its place."""

    async def fake(cases, **kwargs):
        calls.append({"cases": cases, **kwargs})
        for item in items:
            if isinstance(item, Exception):
                raise item
            yield item

    return fake


def _frames(response_text: str) -> list[Any]:
    frames: list[Any] = []
    for line in response_text.splitlines():
        if line.startswith("data: "):
            payload = line[len("data: ") :]
            frames.append("complete" if payload == "complete" else json.loads(payload))
    return frames


class TestGroundCasesRoute:
    def test_frames_for_grounded_and_dropped_cases(self, client, project_task_server):
        _project, _task, server = project_task_server
        calls: list[dict[str, Any]] = []
        usage = Usage(input_tokens=10, output_tokens=2, cost=0.5)
        fake = _fake_ground_cases(
            [
                CaseGrounded(1, _dropped()),
                CaseGrounded(0, _grounded(server)),
                GroundingFinished(
                    grounded=1, dropped=1, usage=usage, usage_complete=True
                ),
            ],
            calls,
        )
        with patch(f"{SERVICE}.ground_cases", new=fake):
            resp = client.post(GROUND_URL, json=_request(server))

        assert resp.status_code == 200, resp.text
        frames = _frames(resp.text)
        assert [f if isinstance(f, str) else f["type"] for f in frames] == [
            "grounding_started",
            "case_dropped",
            "case_grounded",
            "grounding_finished",
            "complete",
        ]
        assert frames[0] == {"type": "grounding_started", "total": 2}
        assert frames[1] == {
            "type": "case_dropped",
            "case_index": 1,
            "scenario_index": 4,
            "drop_reason": "no_fit",
            "drop_detail": "No ticket is assigned to a support lead.",
        }
        grounded = frames[2]
        assert grounded["case_index"] == 0
        assert grounded["scenario_index"] == 3
        assert grounded["status"] == "grounded"
        assert grounded["openenv_reset"] == {
            "openenv_server_id": server.id,
            "reset_kwargs": {"fixture_id": "f1"},
        }
        assert grounded["seed_prompt"] == "Close ticket 7 please."
        assert grounded["synthetic_user_info"] == USER_INFO
        assert grounded["judge_guidance"].startswith(
            "## Starting point\nTicket 7 is open."
        )
        assert "Checked with `read_notes`" in grounded["judge_guidance"]
        assert "reference" not in grounded
        finished = frames[3]
        assert (finished["grounded"], finished["dropped"]) == (1, 1)
        assert finished["usage"]["cost"] == 0.5
        assert finished["usage_complete"] is True

        (call,) = calls
        assert [c.scenario for c in call["cases"]] == ["scenario 0", "scenario 1"]
        assert call["openenv_server"].id == server.id
        assert call["model_name"] == "claude_opus_4_5"
        assert call["model_provider"] == ModelProviderName.anthropic
        context = call["eval_context"]
        assert context.specification == "The agent closes the right ticket."
        assert context.target_task_prompt == "You help with tickets."
        assert context.data_guide == "Support leads triaging tickets."
        # The agent under test's tools, read from the server without an episode.
        assert [t["function"]["name"] for t in call["target_tools"]] == ["read_notes"]

    def test_unreachable_server_fails_the_stream_with_its_url(
        self, client, project_task_server
    ):
        _project, _task, server = project_task_server
        fake = _fake_ground_cases(
            [GroundingCaseError(0, OpenEnvError("Could not open a session"))], []
        )
        with patch(f"{SERVICE}.ground_cases", new=fake):
            resp = client.post(GROUND_URL, json=_request(server))

        frames = _frames(resp.text)
        assert frames[-2]["type"] == "grounding_failed"
        assert frames[-2]["code"] == "openenv_unreachable"
        assert server.url in frames[-2]["message"]
        assert "Could not open a session" in frames[-2]["message"]
        assert frames[-1] == "complete"

    def test_a_provider_error_fails_the_stream(self, client, project_task_server):
        _project, _task, server = project_task_server
        fake = _fake_ground_cases(
            [
                CaseGrounded(0, _grounded(server)),
                GroundingCaseError(1, RuntimeError("provider down")),
            ],
            [],
        )
        with patch(f"{SERVICE}.ground_cases", new=fake):
            resp = client.post(GROUND_URL, json=_request(server))

        frames = _frames(resp.text)
        assert [f if isinstance(f, str) else f["type"] for f in frames] == [
            "grounding_started",
            "case_grounded",
            "grounding_failed",
            "complete",
        ]
        assert frames[2] == {
            "type": "grounding_failed",
            "code": "grounding_error",
            "message": "RuntimeError: provider down",
        }

    def test_run_config_without_openenv_tools_is_400(self, client, project_task_server):
        _project, _task, server = project_task_server
        body = _request(
            server,
            target_run_config=_run_config(["kiln_tool::add_numbers"]).model_dump(
                mode="json"
            ),
        )
        resp = client.post(GROUND_URL, json=body)
        assert resp.status_code == 400
        assert resp.json()["message"]["code"] == "no_openenv_server"

    def test_unknown_field_is_422(self, client, project_task_server):
        _project, _task, server = project_task_server
        resp = client.post(GROUND_URL, json=_request(server, judge="x"))
        assert resp.status_code == 422

    def test_single_turn_task_is_400(self, client, project_task_server):
        project, _task, server = project_task_server
        single_turn = Task(name="single", instruction="Answer.", parent=project)
        with patch(f"{API}.task_from_id", return_value=single_turn):
            resp = client.post(GROUND_URL, json=_request(server))
        assert resp.status_code == 400
        assert resp.json()["message"]["code"] == "task_not_multiturn"


class TestClientAbort:
    async def test_closing_the_stream_ends_every_open_episode(
        self, project_task_server, session_manager
    ):
        """Case 0 finishes; case 1 holds an episode on the one-session server until
        the client goes away. Closing the SSE stream must end that episode."""
        _project, task, server = project_task_server
        episode_open = asyncio.Event()

        async def fake_ground_case(case, *, session_manager, openenv_server, **_):
            if case.scenario == "scenario 0":
                return _grounded(openenv_server)
            episode = await session_manager.start_episode(openenv_server, {})
            episode_open.set()
            try:
                await asyncio.Event().wait()
            finally:
                await session_manager.release(episode)
            raise AssertionError("unreachable")

        frames = grounding_frames(
            task=task,
            run_config=_run_config([build_openenv_tool_id(server.id, "read_notes")]),
            openenv_server=server,
            session_manager=session_manager,
            model=GroundingModelApi(
                model_name="claude_opus_4_5", model_provider=ModelProviderName.anthropic
            ),
            specification="spec",
            synthetic_user_guide=None,
            cases=[GroundCaseApi.model_validate(_case(i)) for i in range(2)],
        )
        stream = _grounding_sse(frames)
        with patch("kiln_ai.eval_grounding.batch.ground_case", new=fake_ground_case):
            assert '"grounding_started"' in await anext(stream)
            assert '"case_grounded"' in await anext(stream)
            await asyncio.wait_for(episode_open.wait(), timeout=10)
            await stream.aclose()

        checker = OpenEnvSessionManager()
        try:
            await checker.release(await checker.start_episode(server, {}))
        finally:
            await checker.shutdown()
