import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import litellm
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, TurnMode
from kiln_ai.datamodel.openenv import OpenEnvEpisode, OpenEnvReset, OpenEnvServer
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
    JudgeConfig,
)
from app.desktop.studio_server.eval_builder_api import (
    _grounding_sse,
    _rehearsal_judge,
    connect_eval_builder_api,
)
from app.desktop.studio_server.services.eval_grounding import (
    NoGroundingServerError,
    check_grounded_servers,
    grounding_frames,
)
from app.desktop.studio_server.utils.eval_builder_utils import JudgeVerdict

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
        "grounding_model": {
            "model_name": "claude_opus_4_5",
            "model_provider": "anthropic",
        },
        "specification": "The agent closes the right ticket.",
        "data_guide": "Support leads triaging tickets.",
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
        expected_outcome="Ticket 7 is closed. Ticket 8 stays open.",
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
        assert grounded["input"] is None
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
        assert context.mode == "multi_turn"
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

    def test_the_judge_thinking_level_runs_the_grounding_agent(
        self, client, project_task_server
    ):
        _project, _task, server = project_task_server
        calls: list[dict[str, Any]] = []
        fake = _fake_ground_cases(
            [
                GroundingFinished(
                    grounded=0, dropped=0, usage=Usage(), usage_complete=True
                )
            ],
            calls,
        )
        body = _request(
            server,
            grounding_model={
                "model_name": "claude_opus_4_5",
                "model_provider": "anthropic",
                "thinking_level": "high",
            },
        )
        with patch(f"{SERVICE}.ground_cases", new=fake):
            resp = client.post(GROUND_URL, json=body)
        assert resp.status_code == 200, resp.text
        assert calls[0]["thinking_level"] == "high"

    def test_a_thinking_level_the_model_lacks_is_422(self, client, project_task_server):
        _project, _task, server = project_task_server
        body = _request(
            server,
            grounding_model={
                "model_name": "claude_opus_4_5",
                "model_provider": "anthropic",
                "thinking_level": "not_a_level",
            },
        )
        resp = client.post(GROUND_URL, json=body)
        assert resp.status_code == 422

    def test_unknown_field_is_422(self, client, project_task_server):
        _project, _task, server = project_task_server
        resp = client.post(GROUND_URL, json=_request(server, judge="x"))
        assert resp.status_code == 422

    def _single_turn_request(self, server, **overrides):
        return _request(
            server,
            cases=[{"scenario_index": 0, "scenario": "scenario 0"}],
            **overrides,
        )

    def _single_turn_outcome(self, server) -> GroundingOutcome:
        return _grounded(server).model_copy(
            update={
                "seed_prompt": None,
                "synthetic_user_info": None,
                "input": '{"q": "Is ticket 7 open?"}',
            }
        )

    def test_a_single_turn_task_grounds_in_single_turn_mode(
        self, client, project_task_server
    ):
        project, _task, server = project_task_server
        single_turn = Task(name="single", instruction="Answer.", parent=project)
        calls: list[dict[str, Any]] = []
        fake = _fake_ground_cases(
            [
                CaseGrounded(0, self._single_turn_outcome(server)),
                GroundingFinished(
                    grounded=1, dropped=0, usage=Usage(), usage_complete=True
                ),
            ],
            calls,
        )
        with (
            patch(f"{API}.task_from_id", return_value=single_turn),
            patch(f"{SERVICE}.ground_cases", new=fake),
        ):
            resp = client.post(
                GROUND_URL,
                json=self._single_turn_request(server, example_input="Is it open?"),
            )
        assert resp.status_code == 200, resp.text
        grounded = next(
            f
            for f in _frames(resp.text)
            if isinstance(f, dict) and f["type"] == "case_grounded"
        )
        assert grounded["input"] == '{"q": "Is ticket 7 open?"}'
        assert grounded["seed_prompt"] is None
        assert grounded["synthetic_user_info"] is None
        (call,) = calls
        assert call["cases"][0].mode == "single_turn"
        context = call["eval_context"]
        assert context.mode == "single_turn"
        assert context.example_input == "Is it open?"
        assert context.input_schema is None

    def test_a_structured_input_task_sends_its_schema(
        self, client, project_task_server
    ):
        project, _task, server = project_task_server
        schema = '{"type": "object", "properties": {"q": {"type": "string"}}}'
        structured = Task(
            name="structured",
            instruction="Answer.",
            input_json_schema=schema,
            parent=project,
        )
        calls: list[dict[str, Any]] = []
        fake = _fake_ground_cases(
            [
                CaseGrounded(0, self._single_turn_outcome(server)),
                GroundingFinished(
                    grounded=1, dropped=0, usage=Usage(), usage_complete=True
                ),
            ],
            calls,
        )
        with (
            patch(f"{API}.task_from_id", return_value=structured),
            patch(f"{SERVICE}.ground_cases", new=fake),
        ):
            resp = client.post(GROUND_URL, json=self._single_turn_request(server))
        assert resp.status_code == 200, resp.text
        (call,) = calls
        assert call["eval_context"].mode == "single_turn"
        assert call["eval_context"].input_schema == structured.input_json_schema

    def test_a_single_turn_case_on_a_multi_turn_task_is_422(
        self, client, project_task_server
    ):
        _project, _task, server = project_task_server
        resp = client.post(GROUND_URL, json=self._single_turn_request(server))
        assert resp.status_code == 422
        assert "seed_prompt and synthetic_user_info" in resp.text

    def test_a_drafted_user_on_a_single_turn_task_is_422(
        self, client, project_task_server
    ):
        project, _task, server = project_task_server
        single_turn = Task(name="single", instruction="Answer.", parent=project)
        with patch(f"{API}.task_from_id", return_value=single_turn):
            resp = client.post(GROUND_URL, json=_request(server))
        assert resp.status_code == 422
        assert "only its scenario" in resp.text

    def test_the_turn_limit_reaches_the_grounding_agent(
        self, client, project_task_server
    ):
        _project, _task, server = project_task_server
        calls: list[dict[str, Any]] = []
        fake = _fake_ground_cases(
            [GroundingFinished(grounded=0, dropped=0, usage=None, usage_complete=True)],
            calls,
        )
        with patch(f"{SERVICE}.ground_cases", new=fake):
            resp = client.post(GROUND_URL, json=_request(server, max_turns=1))
        assert resp.status_code == 200, resp.text
        (call,) = calls
        assert call["eval_context"].max_turns == 1

    @pytest.mark.parametrize("with_judge", [False, True])
    def test_grounding_rehearses_only_when_a_rehearsal_judge_is_asked_for(
        self, client, project_task_server, with_judge
    ):
        _project, _task, server = project_task_server
        calls: list[dict[str, Any]] = []
        fake = _fake_ground_cases(
            [GroundingFinished(grounded=0, dropped=0, usage=None, usage_complete=True)],
            calls,
        )
        request = {"rehearsal_judge": REHEARSAL_JUDGE} if with_judge else {}
        with patch(f"{SERVICE}.ground_cases", new=fake):
            resp = client.post(GROUND_URL, json=_request(server, **request))
        assert resp.status_code == 200, resp.text
        (call,) = calls
        assert call["eval_context"].rehearse is with_judge

    def test_a_turn_limit_on_a_single_turn_task_is_422(
        self, client, project_task_server
    ):
        project, _task, server = project_task_server
        single_turn = Task(name="single", instruction="Answer.", parent=project)
        with patch(f"{API}.task_from_id", return_value=single_turn):
            resp = client.post(
                GROUND_URL, json=self._single_turn_request(server, max_turns=1)
            )
        assert resp.status_code == 422
        assert "max_turns is for multi-turn tasks only" in resp.text

    def test_an_example_input_on_a_multi_turn_task_is_422(
        self, client, project_task_server
    ):
        _project, _task, server = project_task_server
        resp = client.post(
            GROUND_URL, json=_request(server, example_input="Is it open?")
        )
        assert resp.status_code == 422
        assert "single-turn tasks only" in resp.text


REHEARSAL_TRACE: list[dict[str, Any]] = [
    {"role": "system", "content": "You help with tickets."},
    {"role": "user", "content": "Close ticket 7 please."},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "rehearsal_call_0",
                "type": "function",
                "function": {"name": "close_ticket", "arguments": '{"id": 7}'},
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "rehearsal_call_0",
        "content": "closed",
        "is_error": None,
    },
    {"role": "assistant", "content": "Ticket 7 is closed."},
]

REHEARSAL_JUDGE = {
    "prompt": "Pass when the agent closes only the ticket the user means.",
    "model_name": "claude_opus_4_5",
    "model_provider": "anthropic",
}


def _rehearsed(server: OpenEnvServer) -> GroundingOutcome:
    grounded = _grounded(server)
    assert grounded.openenv_reset is not None
    return grounded.model_copy(
        update={
            "rehearsal_trace": REHEARSAL_TRACE,
            "rehearsal_episode": OpenEnvEpisode(
                reset=grounded.openenv_reset,
                episode_id="ep1",
                openenv_version="counter@1",
                final_state={"closed": [7]},
            ),
        }
    )


def _hooked_ground_cases(items: list[Any]):
    """Yields `items` in order, calling on_grounded for each grounded case first, as
    the core batch does."""

    async def fake(cases, **kwargs):
        on_grounded = kwargs.get("on_grounded")
        for item in items:
            if (
                on_grounded is not None
                and isinstance(item, CaseGrounded)
                and item.outcome.status == "grounded"
            ):
                await on_grounded(item.case_index, item.outcome)
            yield item

    return fake


class TestRehearsalCheck:
    def _post(self, client, server, judge, *, outcome=None, **request):
        fake = _hooked_ground_cases(
            [
                CaseGrounded(0, outcome or _rehearsed(server)),
                GroundingFinished(
                    grounded=1,
                    dropped=0,
                    usage=Usage(cost=1.0),
                    usage_complete=True,
                ),
            ]
        )
        with (
            patch(f"{SERVICE}.ground_cases", new=fake),
            patch(f"{API}.run_judge_for_trace", new=judge),
        ):
            resp = client.post(GROUND_URL, json=_request(server, **request))
        assert resp.status_code == 200, resp.text
        frames = _frames(resp.text)
        return frames[1], frames[2]

    @pytest.mark.parametrize("score", ["pass", "fail"])
    def test_the_rehearsal_is_judged_and_the_case_kept(
        self, client, project_task_server, score
    ):
        _project, _task, server = project_task_server
        judge = AsyncMock(
            return_value=JudgeVerdict(
                score, "Only ticket 7 changed.", usage=Usage(cost=0.04)
            )
        )
        grounded, finished = self._post(
            client, server, judge, rehearsal_judge=REHEARSAL_JUDGE
        )

        assert grounded["type"] == "case_grounded"
        assert grounded["rehearsal_score"] == score
        assert grounded["rehearsal_reasoning"] == "Only ticket 7 changed."
        assert finished["usage"]["cost"] == 1.0
        assert finished["rehearsal_judge_usage"]["cost"] == 0.04
        judge.assert_awaited_once()
        assert judge.await_args is not None
        args, kwargs = judge.await_args
        assert args[:3] == ("p1", "t1", "Close ticket 7 please.")
        assert "Ticket 7 is closed." in args[3]
        assert args[4] == JudgeConfig.model_validate(REHEARSAL_JUDGE)
        assert kwargs["trace"] == REHEARSAL_TRACE
        assert kwargs["judge_guidance"] == grounded["judge_guidance"]
        assert kwargs["openenv_episode"].final_state == {"closed": [7]}

    def test_no_judge_asked_for_means_no_judge_call(self, client, project_task_server):
        _project, _task, server = project_task_server
        judge = AsyncMock()
        grounded, finished = self._post(client, server, judge)

        judge.assert_not_called()
        assert grounded["rehearsal_score"] is None
        assert grounded["rehearsal_reasoning"] is None
        assert finished["rehearsal_judge_usage"] is None

    def test_a_case_without_a_rehearsal_is_not_judged(
        self, client, project_task_server
    ):
        _project, _task, server = project_task_server
        judge = AsyncMock()
        grounded, finished = self._post(
            client,
            server,
            judge,
            outcome=_grounded(server),
            rehearsal_judge=REHEARSAL_JUDGE,
        )

        judge.assert_not_called()
        assert grounded["rehearsal_score"] is None
        assert finished["rehearsal_judge_usage"] is None

    def test_a_judge_error_leaves_the_case_unjudged(self, client, project_task_server):
        _project, _task, server = project_task_server
        judge = AsyncMock(side_effect=ValueError("Judge returned no score."))
        grounded, finished = self._post(
            client, server, judge, rehearsal_judge=REHEARSAL_JUDGE
        )

        assert grounded["type"] == "case_grounded"
        assert grounded["rehearsal_score"] is None
        assert finished["type"] == "grounding_finished"
        assert finished["rehearsal_judge_usage"] is None

    def test_a_slow_judge_times_out_and_leaves_the_case_unjudged(
        self, client, project_task_server
    ):
        _project, _task, server = project_task_server

        async def slow(*_args: Any, **_kwargs: Any) -> JudgeVerdict:
            await asyncio.sleep(5)
            return JudgeVerdict("pass", "late")

        with patch(f"{SERVICE}.REHEARSAL_JUDGE_TIMEOUT_S", 0.01):
            grounded, finished = self._post(
                client, server, slow, rehearsal_judge=REHEARSAL_JUDGE
            )

        assert grounded["rehearsal_score"] is None
        assert finished["type"] == "grounding_finished"

    async def test_the_judge_retries_a_transient_error(self):
        judge = AsyncMock(
            side_effect=[
                litellm.RateLimitError(
                    message="upstream rate limit",
                    llm_provider="anthropic",
                    model="claude_opus_4_5",
                ),
                JudgeVerdict("pass", "fine"),
            ]
        )
        rehearsal_judge = _rehearsal_judge(
            "p1", "t1", JudgeConfig.model_validate(REHEARSAL_JUDGE)
        )
        with (
            patch(f"{API}.run_judge_for_trace", new=judge),
            patch(f"{API}.asyncio.sleep", new_callable=AsyncMock),
        ):
            verdict = await rehearsal_judge(
                REHEARSAL_TRACE,
                "guidance",
                OpenEnvEpisode(
                    reset=OpenEnvReset(openenv_server_id="s", reset_kwargs={}),
                    episode_id="ep1",
                    openenv_version="counter@1",
                ),
            )

        assert verdict.judge_score == "pass"
        assert judge.await_count == 2


class TestCheckGroundedServers:
    def test_inputs_on_the_run_config_server_pass(self, project_task_server):
        project, _task, server = project_task_server
        run_config = _run_config([build_openenv_tool_id(server.id, "read_notes")])
        check_grounded_servers(project, run_config, [server.id, server.id])

    def test_an_input_on_another_server_is_refused(self, project_task_server):
        project, _task, server = project_task_server
        run_config = _run_config([build_openenv_tool_id(server.id, "read_notes")])
        with pytest.raises(NoGroundingServerError, match="Input 1 is grounded"):
            check_grounded_servers(project, run_config, [server.id, "other"])

    def test_a_run_config_without_a_server_is_refused(self, project_task_server):
        project, _task, server = project_task_server
        with pytest.raises(NoGroundingServerError):
            check_grounded_servers(project, _run_config([]), [server.id])


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
            data_guide=None,
            example_input=None,
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
