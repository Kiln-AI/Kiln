import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import litellm
import pytest
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.build_claim_evidence_output import (
    BuildClaimEvidenceOutput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.refine_judge_prompt_output import (
    RefineJudgePromptOutput,
)
from app.desktop.studio_server.api_models.eval_builder_models import (
    BuildClaimsApiOutput,
    CitationApi,
    ClaimApi,
    FinalJudgementApi,
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
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
    TaskOutputRatingType,
)
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    ToolsRunConfig,
)
from kiln_ai.datamodel.eval import (
    EvalConfigType,
    EvalDataType,
    LlmJudgeProperties,
    SkippedReason,
    V2EvalResult,
)
from kiln_ai.synthetic_user.runner import NUM_CASES_MAX
from kiln_server.custom_errors import connect_custom_errors
from kiln_server.utils.spec_utils import spec_eval_output_score

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
        expected_result="fail",
        evidence="The reply gives a window of 30 days from purchase [1].",
        citations=[
            CitationApi.model_validate(
                {"marker": 1, "source": "output", "from": "30 days", "to": "purchase"}
            )
        ],
    )


def _final_judgement() -> FinalJudgementApi:
    return FinalJudgementApi(
        claim="Fails Eval: the agent fabricated an unverified policy.",
        expected_result="fail",
        evidence="It asserts a return window it never verified [1].",
        citations=[
            CitationApi.model_validate(
                {"marker": 1, "source": "output", "from": "30 days", "to": "purchase"}
            )
        ],
    )


def _claims_output(claims: list[ClaimApi] | None = None) -> BuildClaimsApiOutput:
    return BuildClaimsApiOutput(
        claims=claims if claims is not None else [_claim_with_citation()],
        final_judgement=_final_judgement(),
    )


# ───────────────────────── review_traces (SSE) ─────────────────────────


@pytest.fixture
def review_request():
    return {
        "traces": [
            {"raw_input": "in-1", "raw_output": "out-1"},
            {"raw_input": "in-2", "raw_output": "out-2"},
        ],
        "spec_name": "Test Spec",
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
            new=AsyncMock(return_value=JudgeVerdict("fail", "fabricated a policy")),
        ),
        patch(
            "app.desktop.studio_server.eval_builder_api.build_claims_for_trace",
            new=AsyncMock(return_value=_claims_output()),
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

    # every reviewed event carries the verdict + claims + the top-level final
    # judgement, and the citation key is the literal `from` (the UI greps it),
    # not `from_`.
    for e in reviewed:
        assert e["judge_score"] == "fail"
        # The event echoes the exact text the claim builder saw.
        assert e["raw_input"] in {"in-1", "in-2"}
        assert e["raw_output"] in {"out-1", "out-2"}
        assert e["claims"][0]["expected_result"] == "fail"
        assert e["final_judgement"]["expected_result"] == "fail"
        citation = e["claims"][0]["citations"][0]
        assert citation["from"] == "30 days" and "from_" not in citation
        assert citation["source"] == "output"
        fj_citation = e["final_judgement"]["citations"][0]
        assert fj_citation["from"] == "30 days" and "from_" not in fj_citation


def test_review_traces_supports_empty_claims(client, review_request):
    # claims may be EMPTY (trivial single-property evals) — the final
    # judgement alone carries the review.
    with (
        patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=AsyncMock(return_value=JudgeVerdict("fail", "fabricated a policy")),
        ),
        patch(
            "app.desktop.studio_server.eval_builder_api.build_claims_for_trace",
            new=AsyncMock(return_value=_claims_output(claims=[])),
        ),
    ):
        resp = client.post(REVIEW_URL, json=review_request)

    assert resp.status_code == 200
    reviewed = [
        e
        for e in _parse_sse(resp.text)
        if isinstance(e, dict) and e.get("type") == "trace_reviewed"
    ]
    assert len(reviewed) == 2
    for e in reviewed:
        assert e["claims"] == []
        assert e["final_judgement"]["expected_result"] == "fail"


def test_review_traces_emits_trace_error_and_still_completes(client, review_request):
    # Judge succeeds; the claim step fails → each trace becomes a trace_error,
    # but the batch keeps going and still terminates cleanly.
    with (
        patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=AsyncMock(return_value=JudgeVerdict("pass", "fine")),
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
    assert all(e["code"] == "review_failed" for e in errors)
    assert all("boom" in e["message"] for e in errors)
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

    def test_multi_turn_uses_canonical_transcript_block(self):
        template = build_judge_prompt_template("Check the policy.", multi_turn=True)
        assert "Check the policy." in template
        # format_trace = the shared canonical rendering (EvalTraceFormatter),
        # the same text the claim builder receives as raw_output.
        assert "{{ trace | format_trace }}" in template
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
            in_memory_task, judge_config, multi_turn=False, spec_name="Test Spec"
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
        # The review judge scores under the SAME identity the saved eval uses
        # (spec_eval_output_score), so the calibrated prompt is the shipped one.
        assert eval_obj.output_scores[0] == spec_eval_output_score("Test Spec")
        assert eval_obj.output_scores[0].json_key() == "test_spec"
        assert eval_obj.parent_task() is in_memory_task

    def test_multi_turn_scores_full_trace(self, in_memory_task, judge_config):
        config = build_transient_judge_eval_config(
            in_memory_task, judge_config, multi_turn=True, spec_name="Test Spec"
        )
        eval_obj = config.parent_eval()
        assert eval_obj is not None
        assert eval_obj.evaluation_data_type == EvalDataType.full_trace
        properties = config.properties
        assert isinstance(properties, LlmJudgeProperties)
        assert "{{ trace | format_trace }}" in properties.prompt_template


class TestRunJudgeForTrace:
    @pytest.mark.asyncio
    async def test_pass_verdict_with_reasoning(self, in_memory_task, judge_config):
        adapter = _judge_adapter(
            V2EvalResult(
                scores={"test_spec": 1.0},
                intermediate_outputs={"reasoning": "The reply follows the policy."},
            )
        )
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            verdict = await run_judge_for_trace(
                "p1", "t1", "in", "out", judge_config, spec_name="Test Spec"
            )

        assert verdict.judge_score == "pass"
        assert verdict.judge_reasoning == "The reply follows the policy."

    @pytest.mark.asyncio
    async def test_fail_verdict_falls_back_when_no_reasoning(
        self, in_memory_task, judge_config
    ):
        adapter = _judge_adapter(V2EvalResult(scores={"test_spec": 0.0}))
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            verdict = await run_judge_for_trace(
                "p1", "t1", "in", "out", judge_config, spec_name="Test Spec"
            )

        assert verdict.judge_score == "fail"
        assert "FAIL" in verdict.judge_reasoning  # honest placeholder, not fabricated

    @pytest.mark.asyncio
    async def test_chain_of_thought_reasoning_fallback(
        self, in_memory_task, judge_config
    ):
        adapter = _judge_adapter(
            V2EvalResult(
                scores={"test_spec": 1.0},
                intermediate_outputs={"chain_of_thought": "Step by step it holds."},
            )
        )
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            verdict = await run_judge_for_trace(
                "p1", "t1", "in", "out", judge_config, spec_name="Test Spec"
            )

        assert verdict.judge_reasoning == "Step by step it holds."

    @pytest.mark.asyncio
    async def test_multi_turn_passes_trace_and_final_message(
        self, in_memory_task, judge_config
    ):
        adapter = _judge_adapter(V2EvalResult(scores={"test_spec": 1.0}))
        trace = [
            {"role": "user", "content": "Can I return opened items?"},
            {"role": "assistant", "content": "Let me check the policy."},
            {"role": "user", "content": "Please do."},
            {"role": "assistant", "content": "Yes, within 30 days."},
        ]
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch as mock_registry:
            await run_judge_for_trace(
                "p1",
                "t1",
                "in",
                "flattened transcript",
                judge_config,
                spec_name="Test Spec",
                trace=trace,
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
                await run_judge_for_trace(
                    "p1", "t1", "in", "out", judge_config, spec_name="Test Spec"
                )

    @pytest.mark.asyncio
    async def test_missing_score_raises(self, in_memory_task, judge_config):
        adapter = _judge_adapter(V2EvalResult(scores={}))
        task_patch, registry_patch = _patch_judge_seam(in_memory_task, adapter)
        with task_patch, registry_patch:
            with pytest.raises(ValueError, match="no score"):
                await run_judge_for_trace(
                    "p1", "t1", "in", "out", judge_config, spec_name="Test Spec"
                )


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
    assert all("Judge skipped this trace" in e["message"] for e in errors)
    assert all("missing_trace" in e["message"] for e in errors)
    assert events[-1] == "complete"


def test_review_traces_rejects_retired_trace_key(client, review_request):
    # Multi-turn traces never ride this request (the review pipeline drives
    # and reviews them server-side); a stale client sending `trace` must
    # fail loudly, not have its trace silently dropped.
    review_request["traces"][0]["trace"] = [{"role": "user", "content": "hi"}]
    resp = client.post(REVIEW_URL, json=review_request)
    assert resp.status_code == 422


def test_review_traces_rejects_sourceless_trace(client, review_request):
    review_request["traces"][0] = {}
    resp = client.post(REVIEW_URL, json=review_request)
    assert resp.status_code == 422


def test_review_traces_rejects_oversized_batch(client, review_request):
    review_request["traces"] = [
        {"raw_input": f"in-{i}", "raw_output": f"out-{i}"} for i in range(51)
    ]
    resp = client.post(REVIEW_URL, json=review_request)
    assert resp.status_code == 422


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
        "judge_score": "fail",
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
                    "expected_result": "fail",
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
            ],
            "final_judgement": {
                "claim": "Fails Eval: the agent fabricated an unverified policy.",
                "expected_result": "fail",
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
            assert len(result["claims"]) == 1
            assert result["claims"][0]["expected_result"] == "fail"
            assert result["final_judgement"]["expected_result"] == "fail"

            # The regression that matters: serialized citation key must be `from`
            # — on claims AND on the top-level final judgement.
            citation = result["claims"][0]["citations"][0]
            assert "from" in citation and "from_" not in citation
            assert citation["from"] == "30 days"
            assert citation["to"] == "purchase"
            assert citation["source"] == "output"
            fj_citation = result["final_judgement"]["citations"][0]
            assert "from" in fj_citation and "from_" not in fj_citation
            assert fj_citation["to"] == "full refund"

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


# ───────────────────────── refine_judge ──────────────────────────────────

REFINE_JUDGE_URL = "/api/projects/p1/tasks/t1/eval_builder/refine_judge"


@pytest.fixture
def refine_judge_input():
    return {
        "judge_prompt": "The agent must not fabricate policies. PASS if it hedges, FAIL otherwise.",
        "graded_traces": [
            {
                "trace_label": "leaf-abc",
                "judge_score": "fail",
                "judge_reasoning": "Stated a return window as fact.",
                "claims": [
                    {
                        "claim": "The agent stated an unverified return window as fact.",
                        "evidence": "The reply gives 30 days [1].",
                        "expected_result": "fail",
                        "human_grade": "agree",
                        "human_feedback": None,
                    }
                ],
                "final_judgement": {
                    "claim": "Fails Eval.",
                    "evidence": "Asserts an unverified window [1].",
                    "expected_result": "fail",
                    "human_grade": "disagree",
                    "human_feedback": "The window is actually documented, so this should pass.",
                },
            }
        ],
    }


class TestRefineJudge:
    def test_refine_judge_no_api_key(self, client, refine_judge_input):
        """Fail-fast: a keyless caller gets a clean 401 before the remote call."""
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config = mock_config_shared.return_value
            mock_config.kiln_copilot_api_key = None
            response = client.post(REFINE_JUDGE_URL, json=refine_judge_input)
            assert response.status_code == 401
            assert "API key not configured" in response.json()["message"]

    def test_refine_judge_success(self, client, refine_judge_input, mock_api_key):
        mock_output = MagicMock(spec=RefineJudgePromptOutput)
        mock_output.to_dict.return_value = {
            "refined_judge_prompt": "The agent must not fabricate policies. A specific unverified detail stated as fact is a FAILURE.",
            "changes": [
                {
                    "change": "Made an unverified detail stated as fact an explicit failure.",
                    "rationale": "trace leaf-abc: reviewer disagreed with the fail on a documented window.",
                }
            ],
            "not_incorporated_feedback": None,
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = mock_output

        with patch(
            "app.desktop.studio_server.utils.eval_builder_utils.refine_judge_prompt_v1_copilot_refine_judge_prompt_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(REFINE_JUDGE_URL, json=refine_judge_input)
            assert response.status_code == 200
            result = response.json()
            assert "FAILURE" in result["refined_judge_prompt"]
            assert len(result["changes"]) == 1
            assert result["changes"][0]["rationale"].startswith("trace leaf-abc")
            assert result["not_incorporated_feedback"] is None

    def test_refine_judge_remote_error_surfaces_upstream_message(
        self, client, refine_judge_input, mock_api_key
    ):
        """A remote failure propagates the upstream status + message (the
        custom error handler renders it as {"message": ...} for the UI)."""
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.content = b'{"message": "upstream refused"}'
        mock_response.parsed = None

        with patch(
            "app.desktop.studio_server.utils.eval_builder_utils.refine_judge_prompt_v1_copilot_refine_judge_prompt_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(REFINE_JUDGE_URL, json=refine_judge_input)
            assert response.status_code == 502
            assert "upstream refused" in response.json()["message"]

    def test_refine_judge_no_response_is_500(
        self, client, refine_judge_input, mock_api_key
    ):
        """A 2xx with no parsed body surfaces as a 500 with a clear message."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = None

        with patch(
            "app.desktop.studio_server.utils.eval_builder_utils.refine_judge_prompt_v1_copilot_refine_judge_prompt_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(REFINE_JUDGE_URL, json=refine_judge_input)
            assert response.status_code == 500
            assert "Failed to refine the judge prompt" in response.json()["message"]

    def test_refine_judge_rejects_empty_graded_traces(self, client, mock_api_key):
        """graded_traces must be non-empty (min_length=1) — a 422 before any
        remote call."""
        response = client.post(
            REFINE_JUDGE_URL,
            json={"judge_prompt": "p", "graded_traces": []},
        )
        assert response.status_code == 422


# ───────────────────────── review_pipeline (SSE) ─────────────────────────

PIPELINE_URL = "/api/projects/p1/tasks/t1/eval_builder/review_pipeline"


def _pipeline_case(i: int) -> dict:
    return {
        "seed_prompt": f"seed-{i}",
        "synthetic_user_info": (
            f"<persona>persona-{i}</persona>"
            f"<goal>goal-{i}</goal>"
            f"<behavior_guidance>guide-{i}</behavior_guidance>"
        ),
        "scenario_index": i,
    }


@pytest.fixture
def pipeline_request():
    return {
        "cases": [_pipeline_case(0), _pipeline_case(1)],
        "turns": 2,
        # Inline run config = the FULL properties shape a manual run sends.
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
        "spec_name": "Test Spec",
        "judge": {
            "prompt": "Judge whether the output fabricates policy.",
            "model_name": "claude_sonnet_4_6",
            "model_provider": "anthropic",
        },
    }


# A drive trace shaped like the runner's real traces: system turn, tool
# call, tool result — the full fidelity the judge and claim builder consume.
def _real_trace(i: int) -> list[dict]:
    return [
        {"role": "system", "content": "You are a support agent."},
        {"role": "user", "content": f"question {i}"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup_policy", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "30 day window"},
        {"role": "assistant", "content": f"answer {i}"},
    ]


def _rate_limit_error() -> litellm.RateLimitError:
    """A transient provider error, per the shared retry classifier."""
    return litellm.RateLimitError(
        message="upstream rate limit",
        llm_provider="openrouter",
        model="gpt_5_5",
    )


def _auth_error() -> litellm.AuthenticationError:
    """A config-scoped (batch-fatal) provider error."""
    return litellm.AuthenticationError(
        message="invalid api key",
        llm_provider="openrouter",
        model="gpt_5_5",
    )


def _fake_run_cases_batch(*, fail_case: int | None = None, events_per_case: int = 2):
    """An async-generator stand-in for the libs/core runner: batch_started,
    then per case its turn events and completion (or failure)."""
    from kiln_ai.synthetic_user.runner import (
        BatchCompletedEvent,
        BatchStartedEvent,
        CaseCompletedEvent,
        CaseFailedEvent,
        TurnCompletedEvent,
    )

    async def fake(*, cases, turns, **_kwargs):
        yield BatchStartedEvent(batch_tag="tag123", num_cases=len(cases))
        successful = 0
        failed = 0
        for i in range(len(cases)):
            if fail_case == i:
                yield CaseFailedEvent(
                    case_index=i,
                    error_code="unexpected_error",
                    message="drive blew up",
                )
                failed += 1
                continue
            for _turn in range(turns):
                yield TurnCompletedEvent(
                    case_index=i,
                    turn_index=_turn + 1,
                    assistant_run_id=f"run-{i}",
                    su_next_message="next",
                    cumulative_cost=0.01,
                    trace=_real_trace(i),
                )
            yield CaseCompletedEvent(
                case_index=i,
                chain_run_ids=[f"run-{i}-a", f"run-{i}-b"],
                leaf_run_id=f"leaf-{i}",
                total_turns=turns,
                total_cost=0.05,
            )
            successful += 1
        yield BatchCompletedEvent(
            successful=successful,
            failed=failed,
            batch_tag="tag123",
            total_cost=0.05 * successful,
        )

    return fake


def _multiturn_task_mock():
    from unittest.mock import Mock

    from kiln_ai.datamodel.datamodel_enums import TurnMode
    from kiln_ai.datamodel.task import Task as KilnTask

    task = Mock(spec=KilnTask)
    task.name = "support_agent"
    task.instruction = "You are a customer support agent."
    task.turn_mode = TurnMode.multiturn
    return task


@pytest.fixture
def pipeline_seams():
    """Patch the pipeline's seams: the copilot key, task resolution, the
    drive runner, the judge, and the claim builder. Yields the mocks for
    assertions."""
    with (
        patch(
            "app.desktop.studio_server.eval_builder_api.get_copilot_api_key",
            return_value="test_api_key",
        ),
        patch(
            "app.desktop.studio_server.eval_builder_api.task_from_id",
            return_value=_multiturn_task_mock(),
        ) as task_mock,
        patch(
            "app.desktop.studio_server.eval_builder_api.run_cases_batch",
            new=_fake_run_cases_batch(),
        ),
        patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=AsyncMock(return_value=JudgeVerdict("fail", "fabricated a policy")),
        ) as judge_mock,
        patch(
            "app.desktop.studio_server.eval_builder_api.build_claims_for_trace",
            new=AsyncMock(return_value=_claims_output()),
        ) as claims_mock,
        patch(
            "app.desktop.studio_server.eval_builder_api.delete_multi_turn_batch_chains",
            return_value=0,
        ) as delete_mock,
    ):
        yield {
            "task": task_mock,
            "judge": judge_mock,
            "claims": claims_mock,
            "delete": delete_mock,
        }


def _events_of(events: list, type_name: str) -> list[dict]:
    return [e for e in events if isinstance(e, dict) and e.get("type") == type_name]


class TestReviewPipeline:
    def test_happy_path_full_stream(self, client, pipeline_request, pipeline_seams):
        resp = client.post(PIPELINE_URL, json=pipeline_request)

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.text)

        started = _events_of(events, "batch_started")
        assert started == [
            {"type": "batch_started", "batch_tag": "tag123", "total_cases": 2}
        ]

        turns = _events_of(events, "turn_completed")
        assert len(turns) == 4  # 2 cases x 2 turns
        # Per-case turn counters climb 1..turns, each with the denominator.
        for case_index in (0, 1):
            case_turns = [t for t in turns if t["case_index"] == case_index]
            assert [t["turns_completed"] for t in case_turns] == [1, 2]
            assert all(t["total_turns"] == 2 for t in case_turns)

        driven = _events_of(events, "case_driven")
        assert {(d["case_index"], d["leaf_run_id"]) for d in driven} == {
            (0, "leaf-0"),
            (1, "leaf-1"),
        }

        judged = _events_of(events, "case_judged")
        assert len(judged) == 2
        for e in judged:
            assert e["judge_score"] == "fail"
            assert e["leaf_run_id"] == f"leaf-{e['case_index']}"
            assert e["total_cost"] == 0.05
            # Canonical transcript rendering of the REAL trace: tool calls
            # and tool results are present; the UI never sees a projection.
            assert "<assistant_requested_tool_calls>" in e["raw_output"]
            assert "<tool_tool_message>" in e["raw_output"]
            assert f"answer {e['case_index']}" in e["raw_output"]
            # raw_input = the conversation's opening user message.
            assert e["raw_input"] == f"question {e['case_index']}"
            # No claims on the stream: they're built lazily via build_claims.
            assert "claims" not in e and "final_judgement" not in e

        completed = _events_of(events, "batch_completed")
        assert completed == [
            {
                "type": "batch_completed",
                "judged": 2,
                "failed": 0,
                "batch_tag": "tag123",
                "total_cost": 0.1,
            }
        ]
        assert events[-1] == "complete"

        # The judge received the runner's REAL trace, not a projection.
        for call in pipeline_seams["judge"].call_args_list:
            trace = call.kwargs["trace"]
            assert any(m.get("role") == "system" for m in trace)
            assert any(m.get("role") == "tool" for m in trace)
        # The pipeline never spends on the claim builder — claims are built
        # per opened trace via the build_claims primitive.
        pipeline_seams["claims"].assert_not_called()
        # No replace_batch_tag → no delete.
        pipeline_seams["delete"].assert_not_called()

    def test_drive_failure_is_isolated(self, client, pipeline_request, pipeline_seams):
        """THE failure-isolation contract: a case dying in the drive stage
        must not discard the other case's completed review."""
        with patch(
            "app.desktop.studio_server.eval_builder_api.run_cases_batch",
            new=_fake_run_cases_batch(fail_case=0),
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        events = _parse_sse(resp.text)
        failed = _events_of(events, "case_failed")
        assert failed == [
            {
                "type": "case_failed",
                "case_index": 0,
                "stage": "drive",
                "code": "unexpected_error",
                "message": "drive blew up",
            }
        ]
        judged = _events_of(events, "case_judged")
        assert [e["case_index"] for e in judged] == [1]
        completed = _events_of(events, "batch_completed")[0]
        assert completed["judged"] == 1
        assert completed["failed"] == 1
        assert events[-1] == "complete"

    def test_judge_failure_is_isolated(self, client, pipeline_request, pipeline_seams):
        async def judge(
            _project_id, _task_id, _raw_input, _raw_output, _judge, **kwargs
        ):
            if kwargs["trace"][1]["content"] == "question 0":
                raise ValueError("judge exploded")
            return JudgeVerdict("pass", "fine")

        with patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=AsyncMock(side_effect=judge),
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        events = _parse_sse(resp.text)
        failed = _events_of(events, "case_failed")
        assert len(failed) == 1
        assert failed[0]["case_index"] == 0
        assert failed[0]["stage"] == "judge"
        assert failed[0]["code"] == "judge_failed"
        assert "judge exploded" in failed[0]["message"]
        judged = _events_of(events, "case_judged")
        assert [e["case_index"] for e in judged] == [1]
        assert events[-1] == "complete"

    def test_replace_batch_tags_deleted_after_successful_drive(
        self, client, pipeline_request, pipeline_seams
    ):
        # Aborted re-drives can strand several batches; all of them are
        # cleaned once this drive has produced replacement chains.
        pipeline_request["replace_batch_tags"] = ["oldbatch123", "olderbatch456"]
        resp = client.post(PIPELINE_URL, json=pipeline_request)

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert len(_events_of(events, "case_judged")) == 2
        delete_mock = pipeline_seams["delete"]
        assert [c.args[1] for c in delete_mock.call_args_list] == [
            "oldbatch123",
            "olderbatch456",
        ]

    def test_replace_batch_tag_not_deleted_when_nothing_drove(
        self, client, pipeline_request, pipeline_seams
    ):
        """A wholesale drive failure must keep the superseded batch — the
        user must never end up with neither batch."""

        async def all_fail_runner(*, cases, **_kwargs):
            from kiln_ai.synthetic_user.runner import (
                BatchStartedEvent,
                CaseFailedEvent,
            )

            yield BatchStartedEvent(batch_tag="tag123", num_cases=len(cases))
            for i in range(len(cases)):
                yield CaseFailedEvent(
                    case_index=i, error_code="unexpected_error", message="down"
                )

        pipeline_request["replace_batch_tags"] = ["oldbatch123"]
        with patch(
            "app.desktop.studio_server.eval_builder_api.run_cases_batch",
            new=all_fail_runner,
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        completed = _events_of(events, "batch_completed")[0]
        assert completed["failed"] == 2
        pipeline_seams["delete"].assert_not_called()

    def test_saved_run_config_reaches_the_runner_verbatim(
        self, client, pipeline_request, pipeline_seams
    ):
        """A target_run_config_id resolves to the saved config's properties,
        handed to the runner untouched — tools and sampling included — with
        the config's id for run attribution."""
        rc = Mock()
        rc.id = "rc-1"
        rc.run_config_properties = KilnAgentRunConfigProperties(
            model_name="gpt_5_5",
            model_provider_name=ModelProviderName.openrouter,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
            tools_config=ToolsRunConfig(tools=["kiln_tool::add_numbers"]),
        )
        task = pipeline_seams["task"].return_value
        task.run_configs.return_value = [rc]

        captured: dict = {}
        inner = _fake_run_cases_batch()

        async def capturing(*, cases, turns, **kwargs):
            captured.update(kwargs)
            async for event in inner(cases=cases, turns=turns, **kwargs):
                yield event

        del pipeline_request["target_run_config"]
        pipeline_request["target_run_config_id"] = "rc-1"
        with (
            patch(
                "app.desktop.studio_server.eval_builder_api.run_cases_batch",
                new=capturing,
            ),
            patch(
                "app.desktop.studio_server.eval_api.task_from_id",
                return_value=task,
            ),
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        assert resp.status_code == 200
        assert captured["target_run_config"] is rc.run_config_properties
        assert captured["task_run_config_id"] == "rc-1"

    def test_unknown_run_config_id_is_404_before_the_stream(
        self, client, pipeline_request, pipeline_seams
    ):
        """Resolution happens at construction, so a bad id is a clean 404 —
        never a half-open event stream."""
        task = pipeline_seams["task"].return_value
        task.run_configs.return_value = []
        del pipeline_request["target_run_config"]
        pipeline_request["target_run_config_id"] = "missing"
        with patch(
            "app.desktop.studio_server.eval_api.task_from_id",
            return_value=task,
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)
        assert resp.status_code == 404
        assert resp.json()["message"]["code"] == "run_config_not_found"
        assert not resp.headers["content-type"].startswith("text/event-stream")

    def test_rejects_single_turn_task(self, client, pipeline_request, pipeline_seams):
        from kiln_ai.datamodel.datamodel_enums import TurnMode

        pipeline_seams["task"].return_value.turn_mode = TurnMode.single_turn
        resp = client.post(PIPELINE_URL, json=pipeline_request)
        assert resp.status_code == 400
        assert resp.json()["message"]["code"] == "task_not_multiturn"

    def test_rejects_invalid_case_shape(self, client, pipeline_request, pipeline_seams):
        pipeline_request["cases"] = [{"seed_prompt": "only a seed"}]
        resp = client.post(PIPELINE_URL, json=pipeline_request)
        assert resp.status_code == 400
        assert resp.json()["message"]["code"] == "invalid_case_shape"

    def test_rejects_oversized_batch(self, client, pipeline_request, pipeline_seams):
        pipeline_request["cases"] = [
            _pipeline_case(i) for i in range(NUM_CASES_MAX + 1)
        ]
        resp = client.post(PIPELINE_URL, json=pipeline_request)
        assert resp.status_code == 422

    def test_rejects_unkeyable_spec_name(
        self, client, pipeline_request, pipeline_seams
    ):
        pipeline_request["spec_name"] = "!!!"
        resp = client.post(PIPELINE_URL, json=pipeline_request)
        assert resp.status_code == 422

    def test_drive_crash_surfaces_batch_failed(
        self, client, pipeline_request, pipeline_seams
    ):
        """A runner-level crash (developer bug, not a per-case failure) must
        end the stream with batch_failed — never a clean batch_completed."""

        async def crashing_runner(**_kwargs):
            from kiln_ai.synthetic_user.runner import BatchStartedEvent

            yield BatchStartedEvent(batch_tag="tag123", num_cases=2)
            raise RuntimeError("runner exploded")

        with patch(
            "app.desktop.studio_server.eval_builder_api.run_cases_batch",
            new=crashing_runner,
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        events = _parse_sse(resp.text)
        assert _events_of(events, "batch_completed") == []
        failed = _events_of(events, "batch_failed")
        assert len(failed) == 1
        assert failed[0]["code"] == "internal_error"
        assert "runner exploded" in failed[0]["message"]
        assert events[-1] == "complete"

    def test_judge_transient_failure_retries_then_succeeds(
        self, client, pipeline_request, pipeline_seams
    ):
        """A transient judge failure (shared retry classifier) is retried in
        place — the case still lands as case_judged, never case_failed."""
        calls = {"case_0": 0}

        async def flaky_judge(
            _project_id, _task_id, _raw_input, _raw_output, _judge, **kwargs
        ):
            if kwargs["trace"][1]["content"] == "question 0":
                calls["case_0"] += 1
                if calls["case_0"] == 1:
                    raise _rate_limit_error()
            return JudgeVerdict("pass", "fine")

        with (
            patch(
                "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
                new=AsyncMock(side_effect=flaky_judge),
            ),
            patch(
                "app.desktop.studio_server.eval_builder_api.JUDGE_RETRY_DELAY_SECONDS",
                0,
            ),
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        events = _parse_sse(resp.text)
        assert _events_of(events, "case_failed") == []
        judged = _events_of(events, "case_judged")
        assert sorted(e["case_index"] for e in judged) == [0, 1]
        assert calls["case_0"] == 2  # first attempt + one retry
        completed = _events_of(events, "batch_completed")[0]
        assert completed["judged"] == 2
        assert completed["failed"] == 0

    def test_judge_deterministic_failure_does_not_retry(
        self, client, pipeline_request, pipeline_seams
    ):
        """Deterministic judge failures fail the case on the FIRST attempt —
        retrying a non-transient error would just triple the spend."""
        calls = {"case_0": 0}

        async def broken_judge(
            _project_id, _task_id, _raw_input, _raw_output, _judge, **kwargs
        ):
            if kwargs["trace"][1]["content"] == "question 0":
                calls["case_0"] += 1
                raise ValueError("judge output unparseable")
            return JudgeVerdict("pass", "fine")

        with patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=AsyncMock(side_effect=broken_judge),
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        events = _parse_sse(resp.text)
        failed = _events_of(events, "case_failed")
        assert len(failed) == 1
        assert failed[0]["stage"] == "judge"
        assert calls["case_0"] == 1  # no retry
        assert [e["case_index"] for e in _events_of(events, "case_judged")] == [1]

    def test_judge_batch_fatal_failure_aborts_pipeline(
        self, client, pipeline_request, pipeline_seams
    ):
        """A config-scoped judge failure (dead key, deprecated model) aborts
        the WHOLE batch: one batch_aborted frame in place of batch_completed,
        no per-case failure spam, stream still terminates cleanly."""
        with patch(
            "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
            new=AsyncMock(side_effect=_auth_error()),
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        events = _parse_sse(resp.text)
        aborted = _events_of(events, "batch_aborted")
        assert len(aborted) == 1  # first batch-fatal error wins, exactly once
        assert aborted[0]["stage"] == "judge"
        assert "AuthenticationError" in aborted[0]["error"]
        assert _events_of(events, "batch_completed") == []
        assert _events_of(events, "case_failed") == []
        assert events[-1] == "complete"

    def test_abort_cancels_the_running_drive(
        self, client, pipeline_request, pipeline_seams
    ):
        """The abort reuses the consumer-disconnect teardown: the drive task
        is cancelled mid-flight (AsyncJobRunner then cancels its workers), so
        a doomed batch stops spending instead of driving the queued cases."""
        from kiln_ai.synthetic_user.runner import (
            BatchStartedEvent,
            CaseCompletedEvent,
            TurnCompletedEvent,
        )

        drive_cancelled = {"flag": False}

        async def slow_runner(*, cases, turns, **_kwargs):
            yield BatchStartedEvent(batch_tag="tag123", num_cases=len(cases))
            yield TurnCompletedEvent(
                case_index=0,
                turn_index=1,
                assistant_run_id="run-0",
                su_next_message="next",
                cumulative_cost=0.01,
                trace=_real_trace(0),
            )
            yield CaseCompletedEvent(
                case_index=0,
                chain_run_ids=["run-0-a"],
                leaf_run_id="leaf-0",
                total_turns=turns,
                total_cost=0.05,
            )
            try:
                # Case 1 would take much longer; the abort must not wait it out.
                await asyncio.sleep(30)
                yield CaseCompletedEvent(
                    case_index=1,
                    chain_run_ids=["run-1-a"],
                    leaf_run_id="leaf-1",
                    total_turns=turns,
                    total_cost=0.05,
                )
            except asyncio.CancelledError:
                drive_cancelled["flag"] = True
                raise

        with (
            patch(
                "app.desktop.studio_server.eval_builder_api.run_cases_batch",
                new=slow_runner,
            ),
            patch(
                "app.desktop.studio_server.eval_builder_api.run_judge_for_trace",
                new=AsyncMock(side_effect=_auth_error()),
            ),
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        events = _parse_sse(resp.text)
        assert len(_events_of(events, "batch_aborted")) == 1
        # Case 1 never drove: its 30s of spend was cancelled by the abort.
        assert [e["case_index"] for e in _events_of(events, "case_driven")] == [0]
        assert drive_cancelled["flag"] is True
        assert events[-1] == "complete"

    def test_missing_copilot_key_is_401_before_any_drive(
        self, client, pipeline_request
    ):
        """Fail fast for non-Pro users: without a copilot key the claims
        stage can never succeed, so the request must 4xx before the user
        burns their own model spend driving and judging every case."""
        with (
            patch(
                "app.desktop.studio_server.utils.copilot_utils.Config.shared"
            ) as mock_config,
            patch(
                "app.desktop.studio_server.eval_builder_api.run_cases_batch"
            ) as runner_mock,
        ):
            mock_config.return_value.kiln_copilot_api_key = None
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        assert resp.status_code == 401
        assert "API key not configured" in resp.json()["message"]
        runner_mock.assert_not_called()

    def test_rejects_own_batch_tag_in_replace_list(
        self, client, pipeline_request, pipeline_seams
    ):
        pipeline_request["batch_tag"] = "mybatch"
        pipeline_request["replace_batch_tags"] = ["mybatch"]
        resp = client.post(PIPELINE_URL, json=pipeline_request)
        assert resp.status_code == 422

    def test_rejects_unknown_request_fields(
        self, client, pipeline_request, pipeline_seams
    ):
        """A retired or misspelled field must 422 — silently dropping it can
        disable behavior (e.g. batch cleanup) with no signal."""
        pipeline_request["replace_batch_tag"] = "oldbatch123"
        resp = client.post(PIPELINE_URL, json=pipeline_request)
        assert resp.status_code == 422


# ───────────────────────── preflight_model ─────────────────────────

PREFLIGHT_URL = "/api/projects/p1/tasks/t1/eval_builder/preflight_model"


@pytest.fixture
def preflight_request():
    return {"model_name": "gpt_5_5", "model_provider": "openrouter"}


@pytest.fixture
def preflight_seams():
    """task_from_id (path validation only) + adapter_for_task (the lane)."""
    with (
        patch(
            "app.desktop.studio_server.eval_builder_api.task_from_id"
        ) as mock_task_from_id,
        patch(
            "app.desktop.studio_server.eval_builder_api.adapter_for_task"
        ) as mock_adapter_for_task,
    ):
        mock_task_from_id.return_value = Mock()
        adapter = Mock()
        adapter.invoke = AsyncMock(return_value=Mock())
        mock_adapter_for_task.return_value = adapter
        yield mock_task_from_id, mock_adapter_for_task, adapter


class TestPreflightModel:
    def test_ok(self, client, preflight_request, preflight_seams):
        _, _, adapter = preflight_seams
        resp = client.post(PREFLIGHT_URL, json=preflight_request)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        adapter.invoke.assert_awaited_once_with(input="Say OK")

    def test_config_dead_returns_unwrapped_root_error(
        self, client, preflight_request, preflight_seams
    ):
        """A dead lane 400s with the ROOT provider error, not the KilnRunError
        wrapper's genericized message — the stop banner shows this text."""
        _, _, adapter = preflight_seams
        adapter.invoke = AsyncMock(
            side_effect=KilnRunError(
                "An unexpected error occurred.",
                partial_trace=None,
                original=_auth_error(),
            )
        )
        resp = client.post(PREFLIGHT_URL, json=preflight_request)
        assert resp.status_code == 400
        message = resp.json()["message"]["message"]
        assert "AuthenticationError" in message
        assert "invalid api key" in message
        assert "unexpected error" not in message

    def test_never_persists_and_never_uses_the_real_task(
        self, client, preflight_request, preflight_seams
    ):
        """No TaskRun may land in the dataset (allow_saving=False), and the
        completion runs against a transient one-liner task, not the user's
        task prompt."""
        mock_task_from_id, mock_adapter_for_task, _ = preflight_seams
        resp = client.post(PREFLIGHT_URL, json=preflight_request)
        assert resp.status_code == 200
        kwargs = mock_adapter_for_task.call_args.kwargs
        args = mock_adapter_for_task.call_args.args
        assert kwargs["base_adapter_config"].allow_saving is False
        preflight_task = args[0]
        assert preflight_task is not mock_task_from_id.return_value
        assert preflight_task.name == "preflight_check"
        rcp = kwargs["run_config_properties"]
        assert rcp.model_name == "gpt_5_5"
        assert rcp.model_provider_name == ModelProviderName.openrouter

    def test_unknown_provider_is_rejected_before_any_call(
        self, client, preflight_request, preflight_seams
    ):
        _, mock_adapter_for_task, _ = preflight_seams
        preflight_request["model_provider"] = "not_a_provider"
        resp = client.post(PREFLIGHT_URL, json=preflight_request)
        assert resp.status_code == 422
        mock_adapter_for_task.assert_not_called()
