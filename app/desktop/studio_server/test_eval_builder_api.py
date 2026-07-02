import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.build_claim_evidence_output import (
    BuildClaimEvidenceOutput,
)
from app.desktop.studio_server.api_models.eval_builder_models import (
    CitationApi,
    ClaimApi,
)
from app.desktop.studio_server.eval_builder_api import connect_eval_builder_api
from app.desktop.studio_server.utils.eval_builder_utils import JudgeVerdict
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
