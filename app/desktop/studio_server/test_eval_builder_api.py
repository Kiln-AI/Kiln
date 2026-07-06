import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.build_claim_evidence_output import (
    BuildClaimEvidenceOutput,
)
from app.desktop.studio_server.api_models.eval_builder_models import (
    CitationApi,
    ClaimApi,
    JudgeConfig,
)
from app.desktop.studio_server.eval_builder_api import connect_eval_builder_api
from app.desktop.studio_server.utils.eval_builder_utils import (
    JudgeVerdict,
    build_judge_prompt_template,
    build_transient_judge_eval_config,
    run_judge_for_trace,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalConfigType,
    EvalDataType,
    LlmJudgeProperties,
    SkippedReason,
    V2EvalResult,
)
from kiln_server.custom_errors import connect_custom_errors

REVIEW_URL = "/api/projects/p1/tasks/t1/eval_builder/review_traces"
BUILD_CLAIMS_URL = "/api/projects/p1/tasks/t1/eval_builder/build_claims"


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_eval_builder_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_api_key():
    with patch(
        "app.desktop.studio_server.utils.copilot_utils.Config.shared"
    ) as mock_config_shared:
        mock_config = mock_config_shared.return_value
        mock_config.kiln_copilot_api_key = "test_api_key"
        yield mock_config


def _parse_sse(response_text: str) -> list[dict | str]:
    events: list[dict | str] = []
    for line in response_text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        events.append("complete" if payload == "complete" else json.loads(payload))
    return events


def _claim_with_citation() -> ClaimApi:
    return ClaimApi(
        claim="The agent stated a specific 30-day return window as fact.",
        claim_type="assertion",
        evidence="The reply gives a window of 30 days from purchase [1].",
        citations=[
            CitationApi.model_validate(
                {"marker": 1, "source": "output", "from": "30 days", "to": "purchase"}
            )
        ],
    )


# ───────────────────────── review_traces (SSE) ─────────────────────────


@pytest.fixture
def review_request():
    return {
        "traces": [
            {"raw_input": "in-1", "raw_output": "out-1"},
            {"raw_input": "in-2", "raw_output": "out-2"},
        ],
        "eval_rubric": "The agent must not fabricate company policies.",
        "judge": {
            "prompt": "Judge whether the output fabricates policy.",
            "model_name": "claude_sonnet_4_6",
            "model_provider": "anthropic",
        },
    }


def test_review_traces_streams_reviewed_events(client, review_request):
    with (
        patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=AsyncMock(return_value=JudgeVerdict("FAIL", "fabricated a policy")),
        ),
        patch(
            "app.desktop.studio_server.eval_builder_api.build_claims_for_trace",
            new=AsyncMock(return_value=[_claim_with_citation()]),
        ),
    ):
        resp = client.post(REVIEW_URL, json=review_request)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)

    # batch_started + 2 trace_reviewed + complete
    started = [
        e for e in events if isinstance(e, dict) and e.get("type") == "batch_started"
    ]
    reviewed = [
        e for e in events if isinstance(e, dict) and e.get("type") == "trace_reviewed"
    ]
    assert started and started[0]["total"] == 2
    assert len(reviewed) == 2
    assert {e["trace_index"] for e in reviewed} == {0, 1}
    assert events[-1] == "complete"

    # every reviewed event carries the verdict + claims, and the citation key
    # is the literal `from` (the UI greps it), not `from_`.
    for e in reviewed:
        assert e["judge_score"] == "FAIL"
        assert e["claims"][0]["claim_type"] == "assertion"
        citation = e["claims"][0]["citations"][0]
        assert citation["from"] == "30 days" and "from_" not in citation
        assert citation["source"] == "output"


def test_review_traces_emits_trace_error_and_still_completes(client, review_request):
    # Judge succeeds; the claim step fails → each trace becomes a trace_error,
    # but the batch keeps going and still terminates cleanly.
    with (
        patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=AsyncMock(return_value=JudgeVerdict("PASS", "fine")),
        ),
        patch(
            "app.desktop.studio_server.eval_builder_api.build_claims_for_trace",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        resp = client.post(REVIEW_URL, json=review_request)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    errors = [
        e for e in events if isinstance(e, dict) and e.get("type") == "trace_error"
    ]
    assert len(errors) == 2
    assert all("boom" in e["error"] for e in errors)
    assert events[-1] == "complete"


# ───────────────────────── run_judge_for_trace ─────────────────────────


@pytest.fixture
def judge_config():
    return JudgeConfig(
        prompt="Judge whether the output fabricates policy.",
        model_name="claude_sonnet_4_6",
        model_provider="anthropic",
    )


@pytest.fixture
def in_memory_task():
    return Task(
        name="Test Task",
        instruction="Answer customer questions about return policy.",
        parent=Project(name="Test Project"),
    )


def _judge_adapter(result: V2EvalResult) -> MagicMock:
    adapter = MagicMock()
    adapter.evaluate = AsyncMock(return_value=result)
    return adapter


def _patch_judge_seam(task, adapter):
    """Patch the two SDK touchpoints run_judge_for_trace uses: task loading and
    the V2 adapter registry. Returns the (task_from_id, registry) patchers."""
    return (
        patch(
            "app.desktop.studio_server.utils.eval_builder_utils.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.utils.eval_builder_utils.v2_eval_adapter_from_config",
            return_value=adapter,
        ),
    )


class TestBuildJudgePromptTemplate:
    def test_single_turn_uses_io_blocks(self):
        template = build_judge_prompt_template("Check the policy.", multi_turn=False)
        assert "Check the policy." in template
        assert "{{ task_input }}" in template
        assert "{{ final_message }}" in template
        assert "trace" not in template

    def test_multi_turn_uses_trace_block(self):
        template = build_judge_prompt_template("Check the policy.", multi_turn=True)
        assert "Check the policy." in template
        assert "{{ trace | tojson }}" in template
        assert "{{ final_message }}" not in template

    def test_jinja_in_judge_prompt_is_raw_wrapped(self):
        # Spec text with Jinja syntax must not break rendering or inject template
        # code — it gets wrapped in {% raw %} and survives as a literal.
        template = build_judge_prompt_template(
            "Spec says: {{ never_render_this }}", multi_turn=False
        )
        assert "{% raw %}" in template
        assert "{{ never_render_this }}" in template

    def test_plain_prompt_is_not_wrapped(self):
        template = build_judge_prompt_template("No jinja here.", multi_turn=False)
        assert "{% raw %}" not in template


class TestBuildTransientJudgeEvalConfig:
    def test_single_turn_config_shape(self, in_memory_task, judge_config):
        config = build_transient_judge_eval_config(
            in_memory_task, judge_config, multi_turn=False
        )
        assert config.config_type == EvalConfigType.v2
        properties = config.properties
        assert isinstance(properties, LlmJudgeProperties)
        assert properties.model_name == "claude_sonnet_4_6"
        assert properties.model_provider == "anthropic"
        assert "Judge whether the output fabricates policy." in (
            properties.prompt_template
        )

        eval_obj = config.parent_eval()
        assert eval_obj is not None
        assert eval_obj.evaluation_data_type == EvalDataType.final_answer
        assert len(eval_obj.output_scores) == 1
        assert eval_obj.output_scores[0].type == TaskOutputRatingType.pass_fail
        assert eval_obj.output_scores[0].json_key() == "overall"
        assert eval_obj.parent_task() is in_memory_task

    def test_multi_turn_scores_full_trace(self, in_memory_task, judge_config):
        config = build_transient_judge_eval_config(
            in_memory_task, judge_config, multi_turn=True
        )
        eval_obj = config.parent_eval()
        assert eval_obj is not None
        assert eval_obj.evaluation_data_type == EvalDataType.full_trace
        properties = config.properties
        assert isinstance(properties, LlmJudgeProperties)
        assert "{{ trace | tojson }}" in properties.prompt_template


class TestRunJudgeForTrace:
    @pytest.mark.asyncio
    async def test_pass_verdict_with_reasoning(self, in_memory_task, judge_config):
        adapter = _judge_adapter(
            V2EvalResult(
                scores={"overall": 1.0},
                intermediate_outputs={"reasoning": "The reply follows the policy."},
            )
        )
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            verdict = await run_judge_for_trace("p1", "t1", "in", "out", judge_config)

        assert verdict.judge_score == "PASS"
        assert verdict.judge_reasoning == "The reply follows the policy."

    @pytest.mark.asyncio
    async def test_fail_verdict_falls_back_when_no_reasoning(
        self, in_memory_task, judge_config
    ):
        adapter = _judge_adapter(V2EvalResult(scores={"overall": 0.0}))
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            verdict = await run_judge_for_trace("p1", "t1", "in", "out", judge_config)

        assert verdict.judge_score == "FAIL"
        assert "FAIL" in verdict.judge_reasoning  # honest placeholder, not fabricated

    @pytest.mark.asyncio
    async def test_chain_of_thought_reasoning_fallback(
        self, in_memory_task, judge_config
    ):
        adapter = _judge_adapter(
            V2EvalResult(
                scores={"overall": 1.0},
                intermediate_outputs={"chain_of_thought": "Step by step it holds."},
            )
        )
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            verdict = await run_judge_for_trace("p1", "t1", "in", "out", judge_config)

        assert verdict.judge_reasoning == "Step by step it holds."

    @pytest.mark.asyncio
    async def test_multi_turn_passes_trace_and_final_message(
        self, in_memory_task, judge_config
    ):
        adapter = _judge_adapter(V2EvalResult(scores={"overall": 1.0}))
        trace = [
            {"role": "user", "content": "Can I return opened items?"},
            {"role": "assistant", "content": "Let me check the policy."},
            {"role": "user", "content": "Please do."},
            {"role": "assistant", "content": "Yes, within 30 days."},
        ]
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch as mock_registry:
            await run_judge_for_trace(
                "p1", "t1", "in", "flattened transcript", judge_config, trace=trace
            )

        eval_input = adapter.evaluate.call_args.args[0]
        assert eval_input.trace == trace
        # final_message is the closing assistant message, not the flat transcript
        assert eval_input.final_message == "Yes, within 30 days."
        config = mock_registry.call_args.args[0]
        parent_eval = config.parent_eval()
        assert parent_eval is not None
        assert parent_eval.evaluation_data_type == EvalDataType.full_trace

    @pytest.mark.asyncio
    async def test_skip_raises_instead_of_fake_verdict(
        self, in_memory_task, judge_config
    ):
        adapter = _judge_adapter(
            V2EvalResult(
                skipped_reason=SkippedReason.extraction_failed,
                skipped_detail="Template rendering failed",
            )
        )
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            with pytest.raises(ValueError, match="Judge skipped this trace"):
                await run_judge_for_trace("p1", "t1", "in", "out", judge_config)

    @pytest.mark.asyncio
    async def test_missing_score_raises(self, in_memory_task, judge_config):
        adapter = _judge_adapter(V2EvalResult(scores={}))
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            with pytest.raises(ValueError, match="no score"):
                await run_judge_for_trace("p1", "t1", "in", "out", judge_config)


def test_review_traces_judge_skip_streams_trace_error(
    client, review_request, in_memory_task
):
    # End-to-end through review_one_trace: a skipping judge becomes a trace_error
    # SSE event (never a fabricated verdict) and the batch still completes.
    adapter = _judge_adapter(
        V2EvalResult(
            skipped_reason=SkippedReason.missing_trace,
            skipped_detail="no trace on input",
        )
    )
    task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
    with task_patch, registry_patch:
        resp = client.post(REVIEW_URL, json=review_request)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    errors = [
        e for e in events if isinstance(e, dict) and e.get("type") == "trace_error"
    ]
    assert len(errors) == 2
    assert all("Judge skipped this trace" in e["error"] for e in errors)
    assert all("missing_trace" in e["error"] for e in errors)
    assert events[-1] == "complete"


def test_review_traces_forwards_structured_trace(client, review_request):
    # Multi-turn requests carry the structured trace through to the judge.
    trace = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    review_request["traces"][0]["trace"] = trace
    judge_mock = AsyncMock(return_value=JudgeVerdict("PASS", "fine"))
    with (
        patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=judge_mock,
        ),
        patch(
            "app.desktop.studio_server.eval_builder_api.build_claims_for_trace",
            new=AsyncMock(return_value=[_claim_with_citation()]),
        ),
    ):
        resp = client.post(REVIEW_URL, json=review_request)

    assert resp.status_code == 200
    traces_by_input = {
        call.args[2]: call.kwargs["trace"] for call in judge_mock.call_args_list
    }
    assert traces_by_input["in-1"] == trace
    assert traces_by_input["in-2"] is None


# ───────────────────────── build_claims primitive ─────────────────────────


@pytest.fixture
def build_claims_input():
    return {
        "raw_input": "What's your return window for opened electronics?",
        "raw_output": (
            "Our return window is 30 days from purchase, even for opened "
            "electronics, and you'll get a full refund."
        ),
        "eval_rubric": "The agent must not fabricate or guess at company policies.",
        "judge_reasoning": "Stated a concrete return window as fact without verifying.",
        "judge_score": "FAIL",
    }


class TestBuildClaims:
    def test_build_claims_no_api_key(self, client, build_claims_input):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config = mock_config_shared.return_value
            mock_config.kiln_copilot_api_key = None
            response = client.post(BUILD_CLAIMS_URL, json=build_claims_input)
            assert response.status_code == 401
            assert "API key not configured" in response.json()["message"]

    def test_build_claims_success(self, client, build_claims_input, mock_api_key):
        mock_output = MagicMock(spec=BuildClaimEvidenceOutput)
        # to_dict() mirrors the SDK: citations carry the wire key `from`.
        mock_output.to_dict.return_value = {
            "claims": [
                {
                    "claim": "The agent stated a specific 30-day return window as fact.",
                    "claim_type": "assertion",
                    "evidence": "The reply gives a window of 30 days from purchase [1].",
                    "citations": [
                        {
                            "marker": 1,
                            "source": "output",
                            "from": "30 days",
                            "to": "purchase",
                        }
                    ],
                },
                {
                    "claim": "Fails Eval: the agent fabricated an unverified policy.",
                    "claim_type": "final_judgement",
                    "evidence": "It asserts a return window it never verified [1].",
                    "citations": [
                        {
                            "marker": 1,
                            "source": "output",
                            "from": "30 days",
                            "to": "full refund",
                        }
                    ],
                },
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = mock_output

        with patch(
            "app.desktop.studio_server.utils.eval_builder_utils.build_claim_evidence_v1_copilot_build_claim_evidence_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(BUILD_CLAIMS_URL, json=build_claims_input)
            assert response.status_code == 200
            result = response.json()
            assert len(result["claims"]) == 2
            assert result["claims"][0]["claim_type"] == "assertion"
            assert result["claims"][1]["claim_type"] == "final_judgement"

            # The regression that matters: serialized citation key must be `from`.
            citation = result["claims"][0]["citations"][0]
            assert "from" in citation and "from_" not in citation
            assert citation["from"] == "30 days"
            assert citation["to"] == "purchase"
            assert citation["source"] == "output"

    def test_build_claims_no_response(self, client, build_claims_input, mock_api_key):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = None

        with patch(
            "app.desktop.studio_server.utils.eval_builder_utils.build_claim_evidence_v1_copilot_build_claim_evidence_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(BUILD_CLAIMS_URL, json=build_claims_input)
            assert response.status_code == 500
            assert "Failed to build claims" in response.json()["message"]

    def test_build_claims_validation_error(
        self, client, build_claims_input, mock_api_key
    ):
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.content = b'{"message": "Validation error from server"}'
        mock_response.parsed = None

        with patch(
            "app.desktop.studio_server.utils.eval_builder_utils.build_claim_evidence_v1_copilot_build_claim_evidence_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(BUILD_CLAIMS_URL, json=build_claims_input)
            assert response.status_code == 422
            assert "Validation error from server" in response.json()["message"]
