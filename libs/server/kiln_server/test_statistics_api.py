"""Tests for the statistics endpoint (one route, dispatched by `operation`).

Regression anchors are known worked examples (86.4% pass, n=147 -> SE ~2.8pp;
McNemar discordant counts b=13, c=6, n=104 -> exact two-sided p=0.1671).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiln_server.custom_errors import connect_custom_errors
from kiln_server.statistics_api import connect_statistics_api


@pytest.fixture
def app():
    app = FastAPI()
    connect_statistics_api(app)
    connect_custom_errors(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _run(client: TestClient, operation: str, **kwargs) -> dict:
    """POST a successful call and return the parsed body (asserts 200)."""
    resp = client.post("/api/statistics", json={"operation": operation, **kwargs})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _post(client: TestClient, **body):
    return client.post("/api/statistics", json=body)


def _outcomes(n11, n10, n01, n00):
    """Build two aligned 0/1 arrays with the given 2x2 cell counts."""
    a = [1] * n11 + [1] * n10 + [0] * n01 + [0] * n00
    b = [1] * n11 + [0] * n10 + [1] * n01 + [0] * n00
    return a, b


class TestOperationDispatch:
    def test_unknown_operation_errors(self, client):
        resp = _post(client, operation="ttest", n=10)
        assert resp.status_code == 422
        assert "operation" in resp.text

    def test_missing_operation_errors(self, client):
        resp = _post(client, n=10)
        assert resp.status_code == 422


class TestProportionCI:
    def test_trace_regression_anchor(self, client):
        out = _run(client, "proportion_ci", proportion=0.864, n=147)
        assert out["operation"] == "proportion_ci"
        assert out["successes"] == 127
        assert out["percent"] == 86.4
        assert out["standard_error"] == pytest.approx(0.0283, abs=5e-4)
        assert out["standard_error_pct"] == pytest.approx(2.8, abs=0.1)
        assert out["method"] == "wilson"
        assert out["ci_low_pct"] < out["percent"] < out["ci_high_pct"]

    def test_extreme_proportion_clamped(self, client):
        out = _run(client, "proportion_ci", proportion=0.99, n=104)
        assert out["ci_high"] <= 1.0
        assert out["ci_low"] > 0.9

    def test_higher_confidence_widens_interval(self, client):
        narrow = _run(client, "proportion_ci", proportion=0.864, n=147)
        wide = _run(client, "proportion_ci", proportion=0.864, n=147, confidence=0.99)
        assert (wide["ci_high_pct"] - wide["ci_low_pct"]) > (
            narrow["ci_high_pct"] - narrow["ci_low_pct"]
        )

    def test_missing_n_errors(self, client):
        resp = _post(client, operation="proportion_ci", proportion=0.5)
        assert resp.status_code == 422
        assert "n" in resp.text

    def test_missing_proportion_errors(self, client):
        resp = _post(client, operation="proportion_ci", n=100)
        assert resp.status_code == 422
        assert "proportion" in resp.text

    def test_proportion_out_of_range_errors(self, client):
        resp = _post(client, operation="proportion_ci", proportion=1.4, n=10)
        assert resp.status_code == 422

    def test_non_numeric_proportion_errors(self, client):
        resp = _post(client, operation="proportion_ci", proportion="abc", n=10)
        assert resp.status_code == 422
        assert "proportion" in resp.text


class TestCompareProportions:
    def test_significant_difference(self, client):
        out = _run(
            client,
            "compare_proportions",
            proportion_a=0.864,
            n_a=147,
            proportion_b=0.951,
            n_b=104,
        )
        assert out["method"] == "newcombe_wilson"
        assert out["delta_pct"] > 0
        assert out["ci_low"] > 0
        assert out["significant"] is True
        assert out["bootstrap"] is not None
        assert "mcnemar_paired" in out["note"]

    def test_not_significant(self, client):
        out = _run(
            client,
            "compare_proportions",
            proportion_a=0.50,
            n_a=20,
            proportion_b=0.55,
            n_b=20,
        )
        assert out["significant"] is False
        assert out["ci_low"] < 0 < out["ci_high"]

    def test_negative_delta_sign(self, client):
        out = _run(
            client,
            "compare_proportions",
            proportion_a=0.90,
            n_a=100,
            proportion_b=0.80,
            n_b=100,
        )
        assert out["delta_pct"] < 0

    def test_missing_n_errors(self, client):
        resp = _post(
            client,
            operation="compare_proportions",
            proportion_a=0.8,
            proportion_b=0.9,
            n_b=100,
        )
        assert resp.status_code == 422


class TestMcNemarPaired:
    def test_gold_anchor(self, client):
        # 2x2: n11=51, n10=13 (b), n01=6 (c), n00=34 (n=104) -> exact p=0.1671.
        a, b = _outcomes(51, 13, 6, 34)
        out = _run(client, "mcnemar_paired", outcomes_a=a, outcomes_b=b)
        assert out["table"] == {"n11": 51, "n10": 13, "n01": 6, "n00": 34}
        assert out["discordant_hurt_b"] == 13
        assert out["discordant_helped_c"] == 6
        assert out["p_exact"] == pytest.approx(0.1671, abs=1e-4)
        assert out["chi2_cc"] == pytest.approx(1.895, abs=1e-3)
        assert out["significant"] is False
        assert out["ci_method"] == "newcombe_paired"
        assert out["delta_pct"] == pytest.approx(-6.7, abs=0.1)
        assert "pooling_warning" in out

    def test_significant_when_discordant_lopsided(self, client):
        a, b = _outcomes(60, 2, 30, 50)  # b=2, c=30 -> clearly significant
        out = _run(client, "mcnemar_paired", outcomes_a=a, outcomes_b=b)
        assert out["significant"] is True
        assert out["p_exact"] < 0.05

    def test_no_discordant(self, client):
        a, b = _outcomes(40, 0, 0, 10)
        out = _run(client, "mcnemar_paired", outcomes_a=a, outcomes_b=b)
        assert out["p_exact"] == 1.0
        assert out["significant"] is False

    def test_array_length_mismatch_errors(self, client):
        resp = _post(
            client,
            operation="mcnemar_paired",
            outcomes_a=[1, 0, 1],
            outcomes_b=[1, 0],
        )
        assert resp.status_code == 422
        assert "length" in resp.text.lower()

    def test_non_binary_entry_errors(self, client):
        resp = _post(
            client,
            operation="mcnemar_paired",
            outcomes_a=[1, 0, 2],
            outcomes_b=[1, 0, 1],
        )
        assert resp.status_code == 422

    def test_no_input_errors(self, client):
        resp = _post(client, operation="mcnemar_paired", confidence=0.95)
        assert resp.status_code == 422


class TestComparePaired:
    def test_significant_shift(self, client):
        out = _run(
            client,
            "compare_paired",
            values_a=[1, 2, 3, 4, 5, 6, 7],
            values_b=[1.5, 2.6, 3.4, 4.7, 5.5, 6.8, 7.6],
        )
        assert out["wilcoxon_p"] is not None
        assert out["wilcoxon_p"] < 0.05
        assert out["significant"] is True
        assert out["n_pairs_used"] == 7

    def test_few_nonzero_omits_wilcoxon(self, client):
        out = _run(
            client, "compare_paired", values_a=[1, 2, 3, 4], values_b=[2, 3, 4, 5]
        )
        assert out["wilcoxon_p"] is None
        assert out["wilcoxon_note"] is not None

    def test_drops_nan_pairs(self, client):
        # JSON has no NaN literal; the endpoint drops None pairs the same way.
        out = _run(
            client,
            "compare_paired",
            values_a=[1.0, 2.0, 3.0],
            values_b=[2.0, None, 4.0],
        )
        assert out["n_pairs"] == 3
        assert out["n_pairs_used"] == 2

    def test_no_usable_pairs(self, client):
        out = _run(client, "compare_paired", values_a=[None, None], values_b=[1.0, 2.0])
        assert out["n_pairs_used"] == 0
        assert out["significant"] is None

    def test_length_mismatch_errors(self, client):
        resp = _post(
            client, operation="compare_paired", values_a=[1, 2, 3], values_b=[1, 2]
        )
        assert resp.status_code == 422

    def test_deterministic(self, client):
        first = _run(
            client,
            "compare_paired",
            values_a=[1, 2, 3, 4, 5],
            values_b=[1.4, 2.6, 2.9, 4.2, 5.5],
        )
        second = _run(
            client,
            "compare_paired",
            values_a=[1, 2, 3, 4, 5],
            values_b=[1.4, 2.6, 2.9, 4.2, 5.5],
        )
        assert first == second


class TestEndpointWiring:
    def test_openapi_exposes_operation_enum_and_agent_allow(self, app):
        schema = app.openapi()
        op = schema["paths"]["/api/statistics"]["post"]
        # Agent policy must be allow so the chat precondition lets the call through.
        assert op["x-agent-policy"]["permission"] == "allow"
        # The request schema must expose all four operations.
        request_schema = op["requestBody"]["content"]["application/json"]["schema"]
        ref = request_schema["$ref"].split("/")[-1]
        model = schema["components"]["schemas"][ref]
        assert set(model["properties"]["operation"]["enum"]) == {
            "proportion_ci",
            "compare_proportions",
            "mcnemar_paired",
            "compare_paired",
        }

    def test_api_doc_filename_matches_verifier_convention(self):
        # The kiln-chat precondition derives the api_doc filename from method+path
        # (slash -> underscore, braces stripped). Keep this route's slug stable so
        # the generated `post_api_statistics.md` matches what the verifier expects.
        method, path = "POST", "/api/statistics"
        slug = path.lstrip("/").replace("/", "_").replace("{", "").replace("}", "")
        assert f"{method.lower()}_{slug}.md" == "post_api_statistics.md"
