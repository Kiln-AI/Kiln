import json
from unittest.mock import AsyncMock, MagicMock, patch

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
        "target_run_config": {
            "model_name": "gpt_5_5",
            "model_provider": "openrouter",
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

        reviewed = _events_of(events, "case_reviewed")
        assert len(reviewed) == 2
        for e in reviewed:
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
            # Citations keep the literal `from` key.
            citation = e["claims"][0]["citations"][0]
            assert citation["from"] == "30 days" and "from_" not in citation

        completed = _events_of(events, "batch_completed")
        assert completed == [
            {
                "type": "batch_completed",
                "reviewed": 2,
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
        # The claim builder's rubric is the judge's actual prompt.
        for call in pipeline_seams["claims"].call_args_list:
            assert call.kwargs["eval_rubric"] == (
                "Judge whether the output fabricates policy."
            )
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
        reviewed = _events_of(events, "case_reviewed")
        assert [e["case_index"] for e in reviewed] == [1]
        completed = _events_of(events, "batch_completed")[0]
        assert completed["reviewed"] == 1
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
        reviewed = _events_of(events, "case_reviewed")
        assert [e["case_index"] for e in reviewed] == [1]
        assert events[-1] == "complete"

    def test_claims_failure_is_isolated(self, client, pipeline_request, pipeline_seams):
        async def claims(*, raw_input, **_kwargs):
            if raw_input == "question 1":
                raise RuntimeError("claims exploded")
            return _claims_output()

        with patch(
            "app.desktop.studio_server.eval_builder_api.build_claims_for_trace",
            new=AsyncMock(side_effect=claims),
        ):
            resp = client.post(PIPELINE_URL, json=pipeline_request)

        events = _parse_sse(resp.text)
        failed = _events_of(events, "case_failed")
        assert len(failed) == 1
        assert failed[0]["case_index"] == 1
        assert failed[0]["stage"] == "claims"
        assert failed[0]["code"] == "claims_failed"
        reviewed = _events_of(events, "case_reviewed")
        assert [e["case_index"] for e in reviewed] == [0]
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
        assert len(_events_of(events, "case_reviewed")) == 2
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
        pipeline_request["cases"] = [_pipeline_case(i) for i in range(11)]
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
