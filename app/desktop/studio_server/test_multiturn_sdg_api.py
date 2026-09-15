"""Tests for the multiturn_sdg generate_cases route and the drive request
models and target run config resolver the eval builder's pipelines share.

`task_from_id` / `get_copilot_api_key` / `SyntheticUserClient` are patched
per-test so no real network or filesystem work happens.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.datamodel.datamodel_enums import (
    StructuredOutputMode,
    TurnMode,
)
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    McpRunConfigProperties,
    MCPToolReference,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.synthetic_user.runner import (
    NUM_CASES_MAX,
)
from kiln_server.custom_errors import connect_custom_errors
from pydantic import ValidationError

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    SyntheticUserCase,
)
from app.desktop.studio_server.multiturn_sdg_api import (
    RunCasesBatchApiInput,
    TargetRunConfigFields,
    connect_multiturn_sdg_api,
    resolve_target_run_config,
)
from app.desktop.studio_server.synthetic_user.client import (
    SyntheticUserRequestError,
    SyntheticUserServerError,
)

# ───────────────────────── fixtures ─────────────────────────


@pytest.fixture
def app() -> FastAPI:
    # connect_custom_errors mirrors production: kiln_server.make_app() registers a
    # global HTTPException handler that rewraps `detail` as `{"message": detail}`,
    # so our structured `{"code", "message"}` detail dicts arrive on the wire as
    # `{"message": {"code": ..., "message": ...}}`. Tests must mount the same
    # handler or they assert a wire shape production never ships.
    app = FastAPI()
    connect_custom_errors(app)
    connect_multiturn_sdg_api(app)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _multiturn_task() -> Mock:
    task = Mock(spec=Task)
    task.name = "support_agent"
    task.instruction = "You are a customer support agent."
    task.turn_mode = TurnMode.multiturn
    return task


def _single_turn_task() -> Mock:
    task = Mock(spec=Task)
    task.name = "single_turn_task"
    task.instruction = "Do one thing."
    task.turn_mode = TurnMode.single_turn
    return task


@pytest.fixture
def patch_task_from_id():
    with patch("app.desktop.studio_server.multiturn_sdg_api.task_from_id") as m:
        yield m


@pytest.fixture
def patch_api_key():
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.get_copilot_api_key",
        return_value="test-key",
    ):
        yield


@pytest.fixture
def patch_eval_api_task_from_id():
    """The saved-run-config resolver (task_run_config_from_id) loads the task
    through eval_api's own task_from_id import — patch it alongside ours."""
    with patch("app.desktop.studio_server.eval_api.task_from_id") as m:
        yield m


def _sdk_cases(n: int, with_indices: bool = False) -> list[SyntheticUserCase]:
    return [
        SyntheticUserCase(
            seed_prompt=f"seed-{i}",
            synthetic_user_info=(
                f"<persona>persona-{i}</persona>"
                f"<goal>goal-{i}</goal>"
                f"<behavior_guidance>guide-{i}</behavior_guidance>"
            ),
            scenario_index=i if with_indices else None,
        )
        for i in range(n)
    ]


def _generate_cases_body(num: int = 3) -> dict:
    return {
        "target_specification": "agent waives policy under pressure",
        "num_cases": num,
    }


def _drive_request_body(num: int = 3) -> dict:
    return {
        "cases": [
            {
                "seed_prompt": f"seed-{i}",
                "synthetic_user_info": (
                    f"<persona>persona-{i}</persona>"
                    f"<goal>goal-{i}</goal>"
                    f"<behavior_guidance>guide-{i}</behavior_guidance>"
                ),
            }
            for i in range(num)
        ],
        "turns": 3,
        # The inline run config is the FULL properties shape a manual run
        # sends — tools and sampling ride along, nothing is rebuilt.
        "target_run_config": {
            "model_name": "gpt_5_5",
            "model_provider_name": "openrouter",
            "prompt_id": "simple_prompt_builder",
            "structured_output_mode": "default",
        },
        "su_driver": {
            "model_name": "claude_4_5_haiku",
            "model_provider": "openrouter",
        },
        "batch_tag": "testbatch",
    }


# ───────────────────────── generate_cases ─────────────────────────


def test_generate_cases_happy_path(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(return_value=_sdk_cases(3))

        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=_generate_cases_body(num=3),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cases"]) == 3
    # Cases ride the wire as the SDK shape (seed_prompt + opaque blob).
    case0 = body["cases"][0]
    assert case0["seed_prompt"] == "seed-0"
    assert "<persona>persona-0</persona>" in case0["synthetic_user_info"]


def test_generate_cases_rejects_single_turn_task_with_400(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    patch_task_from_id.return_value = _single_turn_task()

    resp = client.post(
        "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
        json=_generate_cases_body(),
    )

    assert resp.status_code == 400
    assert resp.json()["message"]["code"] == "task_not_multiturn"


def test_generate_cases_does_not_call_upstream_when_guard_fails(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    patch_task_from_id.return_value = _single_turn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=_generate_cases_body(),
        )
        MockClient.assert_not_called()


def test_generate_cases_server_error_surfaces_with_status(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """SyntheticUserServerError with status_code=502 → 502 response."""
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(
            side_effect=SyntheticUserServerError(
                "llm_unavailable", "upstream timed out", status_code=502
            )
        )

        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=_generate_cases_body(),
        )

    assert resp.status_code == 502
    assert resp.json()["message"]["code"] == "llm_unavailable"


def test_generate_cases_request_error_surfaces_as_400(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(
            side_effect=SyntheticUserRequestError(
                "unsupported_model", "no such model", status_code=400
            )
        )

        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=_generate_cases_body(),
        )

    assert resp.status_code == 400
    assert resp.json()["message"]["code"] == "unsupported_model"


def test_generate_cases_validates_num_cases_upper_bound(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """Pydantic should reject NUM_CASES_MAX + 1 before reaching the body."""
    patch_task_from_id.return_value = _multiturn_task()
    resp = client.post(
        "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
        json={"target_specification": "spec", "num_cases": NUM_CASES_MAX + 1},
    )
    assert resp.status_code == 422


def test_generate_cases_accepts_num_cases_at_upper_bound(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """The bound is inclusive: a full-size batch is a valid request."""
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(return_value=_sdk_cases(NUM_CASES_MAX))

        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=_generate_cases_body(num=NUM_CASES_MAX),
        )

    assert resp.status_code == 200, resp.text
    assert len(resp.json()["cases"]) == NUM_CASES_MAX


# ─────────────── generate_cases with per-case prompts (batch plan) ───────────────


def test_generate_cases_with_case_prompts_makes_one_batch_call(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """Plan prompts ride as case_scenarios on ONE upstream call — the spec is
    passed through untouched (scenario composition happens server-side)."""
    patch_task_from_id.return_value = _multiturn_task()
    prompts = ["scenario A", "scenario B", "scenario C"]

    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(return_value=_sdk_cases(3, with_indices=True))

        body = _generate_cases_body(num=3)
        body["case_prompts"] = prompts
        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=body,
        )

    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert [c["seed_prompt"] for c in cases] == ["seed-0", "seed-1", "seed-2"]
    assert [c["scenario_index"] for c in cases] == [0, 1, 2]
    assert instance.generate.await_count == 1
    call = instance.generate.await_args
    assert call.kwargs["case_scenarios"] == prompts
    assert call.kwargs["num_cases"] == 3
    assert call.kwargs["target_specification"] == "agent waives policy under pressure"


def test_generate_cases_salvaged_batch_keeps_scenario_index(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """A scenario batch may come back short (upstream salvage) — the response
    passes the survivors through with their scenario_index mapping intact."""
    patch_task_from_id.return_value = _multiturn_task()
    survivors = _sdk_cases(3, with_indices=True)
    del survivors[1]  # scenario 1's case degraded upstream

    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(return_value=survivors)

        body = _generate_cases_body(num=3)
        body["case_prompts"] = ["a", "b", "c"]
        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=body,
        )

    assert resp.status_code == 200
    cases = resp.json()["cases"]
    assert [c["scenario_index"] for c in cases] == [0, 2]


def test_generate_cases_case_prompts_length_mismatch_is_422(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    patch_task_from_id.return_value = _multiturn_task()
    body = _generate_cases_body(num=3)
    body["case_prompts"] = ["only one prompt"]
    resp = client.post(
        "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
        json=body,
    )
    assert resp.status_code == 422


def test_generate_cases_blank_case_prompt_is_422(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    patch_task_from_id.return_value = _multiturn_task()
    body = _generate_cases_body(num=2)
    body["case_prompts"] = ["real scenario", "   "]
    resp = client.post(
        "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
        json=body,
    )
    assert resp.status_code == 422


def test_generate_cases_scenario_batch_upstream_error_passes_through_typed(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """A scenario batch is one upstream call — its typed failure IS the
    request's failure (no partial batch on the wire)."""
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(
            side_effect=SyntheticUserServerError(
                "llm_unavailable", "upstream timed out", status_code=502
            )
        )

        body = _generate_cases_body(num=3)
        body["case_prompts"] = ["a", "b", "c"]
        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=body,
        )

    assert resp.status_code == 502
    assert resp.json()["message"]["code"] == "llm_unavailable"


def test_generate_cases_empty_upstream_case_list_is_typed_502(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """Upstream promises >= 1 case or a 502; an empty 200 must surface as a
    typed 502, not an empty batch the UI fails on later."""
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(return_value=[])

        body = _generate_cases_body(num=1)
        body["case_prompts"] = ["scenario A"]
        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=body,
        )

    assert resp.status_code == 502
    assert resp.json()["message"]["code"] == "upstream_invalid_output"


# ─────────────── drive request fields and target run config ───────────────
# The eval builder's pipelines inherit these request models and resolve the
# target run config through resolve_target_run_config before opening their
# streams.


def test_drive_request_rejects_both_target_config_sources() -> None:
    body = _drive_request_body()
    body["target_run_config_id"] = "rc-1"
    with pytest.raises(ValidationError, match="exactly one"):
        RunCasesBatchApiInput.model_validate(body)


def test_drive_request_rejects_missing_target_config_source() -> None:
    body = _drive_request_body()
    del body["target_run_config"]
    with pytest.raises(ValidationError, match="exactly one"):
        RunCasesBatchApiInput.model_validate(body)


def test_drive_request_rejects_empty_cases() -> None:
    body = _drive_request_body()
    body["cases"] = []
    with pytest.raises(ValidationError):
        RunCasesBatchApiInput.model_validate(body)


@pytest.mark.parametrize(
    "bad_tag",
    [
        "",  # min_length=1
        "my run",  # space
        "tag:with:colons",  # colon — tag-unsafe (delimiter in our prefix scheme)
        "weird*chars",  # punctuation
        "x" * 65,  # max_length=64
    ],
)
def test_drive_request_rejects_invalid_batch_tags(bad_tag: str) -> None:
    """The batch_tag must be `[A-Za-z0-9_-]{1,64}` — character class and
    length boundaries both enforced. Locks in the rule so a future
    loosening (e.g., adding `:`) doesn't slip past test coverage.
    """
    body = _drive_request_body()
    body["batch_tag"] = bad_tag
    with pytest.raises(ValidationError):
        RunCasesBatchApiInput.model_validate(body)


@pytest.mark.parametrize(
    "good_tag",
    [
        "a",  # min boundary
        "x" * 64,  # max boundary
        "abc-def_123",  # hyphen + underscore + alphanumerics
        "ABC123",  # uppercase
    ],
)
def test_drive_request_accepts_valid_batch_tags(good_tag: str) -> None:
    """Boundary chars that should pass — locks in the accept side of the
    pattern so the test pair fully fences the contract.
    """
    body = _drive_request_body()
    body["batch_tag"] = good_tag
    assert RunCasesBatchApiInput.model_validate(body).batch_tag == good_tag


def test_inline_run_config_has_no_attribution_id() -> None:
    """An inline config is an ad-hoc run — no saved config to attribute to."""
    fields = TargetRunConfigFields.model_validate(
        {"target_run_config": _drive_request_body()["target_run_config"]}
    )
    _, run_config_id = resolve_target_run_config(fields, "proj-1", "task-1")
    assert run_config_id is None


def test_inline_run_config_carries_full_properties() -> None:
    """The inline mode is the FULL properties shape — tools and sampling
    come through verbatim, same fidelity as a saved config."""
    fields = TargetRunConfigFields.model_validate(
        {
            "target_run_config": {
                "model_name": "gpt_5_5",
                "model_provider_name": "openrouter",
                "prompt_id": "simple_prompt_builder",
                "structured_output_mode": "json_schema",
                "temperature": 0.3,
                "tools_config": {"tools": ["kiln_tool::add_numbers"]},
            }
        }
    )
    config, _ = resolve_target_run_config(fields, "proj-1", "task-1")
    assert isinstance(config, KilnAgentRunConfigProperties)
    assert config.tools_config is not None
    assert config.tools_config.tools == ["kiln_tool::add_numbers"]
    assert config.temperature == 0.3
    assert config.structured_output_mode == StructuredOutputMode.json_schema


def test_inline_mcp_run_config_is_400() -> None:
    """An inline MCP-type config can't drive a conversation, same as the
    saved-config path — typed 400 before any stream opens."""
    fields = TargetRunConfigFields.model_validate(
        {
            "target_run_config": {
                "type": "mcp",
                "tool_reference": {"tool_id": "mcp::local::srv::tool"},
            }
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        resolve_target_run_config(fields, "proj-1", "task-1")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "run_config_not_agent"


def test_saved_non_agent_run_config_is_400(patch_eval_api_task_from_id) -> None:
    """An MCP-type saved run config can't drive a conversation — the drive
    loop needs an agent-shaped invoker; surface a typed 400, not a crash."""
    rc = Mock()
    rc.id = "rc-1"
    rc.run_config_properties = McpRunConfigProperties(
        tool_reference=MCPToolReference(tool_id="mcp::local::srv::tool")
    )
    task = _multiturn_task()
    task.run_configs.return_value = [rc]
    patch_eval_api_task_from_id.return_value = task
    fields = TargetRunConfigFields(target_run_config_id="rc-1")
    with pytest.raises(HTTPException) as exc_info:
        resolve_target_run_config(fields, "proj-1", "task-1")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "run_config_not_agent"


def test_generate_cases_preserves_upstream_401_status(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """A 401 from kiln_server means our stored API key is bad — surface
    as 401, not collapsed to a generic 400. Operator-config problem
    surface vs caller-input problem surface should stay distinct.
    """
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(
            side_effect=SyntheticUserRequestError(
                "unauthorized", "bad api key", status_code=401
            )
        )

        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=_generate_cases_body(),
        )

    assert resp.status_code == 401
    assert resp.json()["message"]["code"] == "unauthorized"


def test_generate_cases_preserves_upstream_422_status(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """A 422 from kiln_server (runner sent a body the validator rejected)
    is a different beast from a caller's-input 400 — preserve.
    """
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(
            side_effect=SyntheticUserRequestError(
                "http_422", "body.target_specification: too long", status_code=422
            )
        )

        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=_generate_cases_body(),
        )

    assert resp.status_code == 422
    assert resp.json()["message"]["code"] == "http_422"


def test_generate_cases_preserves_upstream_503_status(
    client: TestClient, patch_task_from_id, patch_api_key
) -> None:
    """An unexpected 5xx (503) should not silently collapse to 500."""
    patch_task_from_id.return_value = _multiturn_task()
    with patch(
        "app.desktop.studio_server.multiturn_sdg_api.SyntheticUserClient"
    ) as MockClient:
        instance = MockClient.return_value
        instance.generate = AsyncMock(
            side_effect=SyntheticUserServerError(
                "http_503", "upstream unavailable", status_code=503
            )
        )

        resp = client.post(
            "/api/projects/proj-1/tasks/task-1/multiturn_sdg/generate_cases",
            json=_generate_cases_body(),
        )

    assert resp.status_code == 503
    assert resp.json()["message"]["code"] == "http_503"
