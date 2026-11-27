import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_server.custom_errors import connect_custom_errors
from pydantic import ValidationError

from app.desktop.studio_server.api_models.eval_builder_models import (
    MAX_GROUPED_FAILURES,
    GroupFailuresApiInput,
)
from app.desktop.studio_server.eval_builder_api import connect_eval_builder_api
from app.desktop.studio_server.services.failure_grouping import (
    GROUPING_INSTRUCTION,
    MAX_GROUPING_INPUT_CHARS,
    UNLABELLED_GROUP,
    FailureGroupingError,
    GroupingAnswer,
    fit_to_budget,
    group_failures,
    grouping_input,
    grouping_output_schema,
    summarize_answer,
)

SERVICE = "app.desktop.studio_server.services.failure_grouping"
URL = "/api/projects/p1/tasks/t1/eval_builder/group_failures"
SPEC = "The agent asks before it deletes any record."


def _failure(case_id: str, reasoning: str = "It deleted without asking.") -> dict:
    return {
        "case_id": case_id,
        "judge_reasoning": reasoning,
        "case_summary": "First message: delete the old ones. Final reply: Done.",
        "judge_guidance": "The agent asks once, then deletes the 3 records.",
    }


def _request(case_ids: tuple[str, ...] = ("a", "b", "c")) -> dict:
    return {
        "spec_text": SPEC,
        "judge": {
            "prompt": "Judge it.",
            "model_name": "claude_sonnet_4_6",
            "model_provider": "anthropic",
            "thinking_level": "high",
        },
        "failures": [_failure(case_id) for case_id in case_ids],
    }


def _answer(**overrides) -> dict:
    answer = {
        "rule_summary": "Asks before deleting a record",
        "groups": [
            {
                "name": "Deleted without asking",
                "fault_kind": "agent",
                "about_rule": True,
            },
            {"name": "Dates shown in UTC", "fault_kind": "agent", "about_rule": False},
            {
                "name": "Expected outcome too strict",
                "fault_kind": "reference",
                "about_rule": True,
            },
        ],
        "failures": [
            {"case_id": "a", "group": "Dates shown in UTC", "evidence": "07/03 shown."},
            {
                "case_id": "b",
                "group": "Deleted without asking",
                "evidence": "No confirm.",
            },
            {
                "case_id": "c",
                "group": "Deleted without asking",
                "evidence": "Deleted 12.",
            },
        ],
    }
    answer.update(overrides)
    return answer


@pytest.fixture
def adapter():
    """The grouping model, answering with _answer() unless a test sets another."""
    adapter = Mock()
    adapter.invoke = AsyncMock(
        return_value=Mock(output=Mock(output=json.dumps(_answer())))
    )
    with patch(f"{SERVICE}.adapter_for_task", return_value=adapter) as factory:
        adapter.factory = factory
        yield adapter


@pytest.fixture
def client():
    app = FastAPI()
    connect_custom_errors(app)
    connect_eval_builder_api(app)
    with patch(
        "app.desktop.studio_server.eval_builder_api.task_from_id",
        return_value=MagicMock(),
    ):
        yield TestClient(app)


class TestSummarizeAnswer:
    def test_counts_groups_largest_first_with_the_first_case_as_example(self):
        result = summarize_answer(
            GroupingAnswer.model_validate(_answer()), ["a", "b", "c"]
        )
        assert [(g.name, g.count) for g in result.groups] == [
            ("Deleted without asking", 2),
            ("Dates shown in UTC", 1),
        ]
        assert result.groups[0].example_case_id == "b"
        assert result.groups[0].example == "No confirm."
        assert result.failure_count == 3

    def test_on_target_counts_only_agent_failures_about_the_rule(self):
        answer = _answer(
            failures=[
                {"case_id": "a", "group": "Dates shown in UTC", "evidence": "."},
                {"case_id": "b", "group": "Deleted without asking", "evidence": "."},
                {
                    "case_id": "c",
                    "group": "Expected outcome too strict",
                    "evidence": ".",
                },
            ]
        )
        result = summarize_answer(
            GroupingAnswer.model_validate(answer), ["a", "b", "c"]
        )
        assert result.on_target_count == 1
        assert [f.fault_kind for f in result.failures] == [
            "agent",
            "agent",
            "reference",
        ]

    def test_keeps_the_request_case_order_and_drops_empty_groups(self):
        answer = _answer(failures=list(reversed(_answer()["failures"])))
        result = summarize_answer(
            GroupingAnswer.model_validate(answer), ["a", "b", "c"]
        )
        assert [f.case_id for f in result.failures] == ["a", "b", "c"]
        assert "Expected outcome too strict" not in [g.name for g in result.groups]

    @pytest.mark.parametrize(
        "answer",
        [
            _answer(failures=_answer()["failures"][:2]),
            _answer(
                failures=[
                    *_answer()["failures"][:2],
                    {"case_id": "c", "group": "Made up", "evidence": "."},
                ]
            ),
        ],
        ids=["left out", "undefined group"],
    )
    def test_a_case_without_a_usable_label_becomes_unknown(self, answer):
        result = summarize_answer(
            GroupingAnswer.model_validate(answer), ["a", "b", "c"]
        )
        assert [(f.case_id, f.fault_kind, f.group) for f in result.failures] == [
            ("a", "agent", "Dates shown in UTC"),
            ("b", "agent", "Deleted without asking"),
            ("c", "unknown", UNLABELLED_GROUP),
        ]
        assert result.groups[-1].name == UNLABELLED_GROUP
        assert result.groups[-1].fault_kind == "unknown"
        assert result.on_target_count == 1

    def test_ignores_extra_labels_and_keeps_the_first_of_each(self):
        answer = _answer(
            groups=[
                *_answer()["groups"],
                {
                    "name": "Dates shown in UTC",
                    "fault_kind": "judge",
                    "about_rule": True,
                },
            ],
            failures=[
                *_answer()["failures"],
                {"case_id": "a", "group": "Deleted without asking", "evidence": "."},
                {"case_id": "zzz", "group": "Dates shown in UTC", "evidence": "."},
            ],
        )
        result = summarize_answer(
            GroupingAnswer.model_validate(answer), ["a", "b", "c"]
        )
        assert [(f.case_id, f.group) for f in result.failures] == [
            ("a", "Dates shown in UTC"),
            ("b", "Deleted without asking"),
            ("c", "Deleted without asking"),
        ]
        assert result.failures[0].fault_kind == "agent"

    def test_cuts_a_long_group_name_instead_of_failing(self):
        long_name = "x" * 300
        answer = _answer(
            groups=[{"name": long_name, "fault_kind": "agent", "about_rule": True}],
            failures=[{"case_id": "a", "group": long_name, "evidence": "."}],
        )
        result = summarize_answer(GroupingAnswer.model_validate(answer), ["a"])
        assert result.groups[0].name == "x" * 120
        assert result.failures[0].group == "x" * 120

    def test_rejects_an_answer_that_labels_no_case(self):
        with pytest.raises(FailureGroupingError, match="labelled none of the cases"):
            summarize_answer(
                GroupingAnswer.model_validate(_answer(failures=[])), ["a", "b", "c"]
            )


class TestFitToBudget:
    def test_leaves_a_small_batch_alone(self):
        failures = GroupFailuresApiInput.model_validate(_request()).failures
        assert fit_to_budget(failures) == (failures, False)

    def test_cuts_every_text_by_the_same_ratio_to_fit(self):
        request = _request(tuple(f"case_{i}" for i in range(MAX_GROUPED_FAILURES)))
        for failure in request["failures"]:
            failure["judge_reasoning"] = "r" * 8000
            failure["case_summary"] = "s" * 4000
        failures = GroupFailuresApiInput.model_validate(request).failures
        fitted, shortened = fit_to_budget(failures)
        assert shortened is True
        total = sum(
            len(f.judge_reasoning) + len(f.case_summary) + len(f.judge_guidance or "")
            for f in fitted
        )
        assert total <= MAX_GROUPING_INPUT_CHARS
        assert len(fitted[0].judge_reasoning) > len(fitted[0].case_summary)
        assert fitted[0].judge_reasoning.startswith("r")
        assert "[…]" in fitted[0].judge_reasoning
        assert [f.case_id for f in fitted] == [f.case_id for f in failures]


class TestGroupFailures:
    async def test_runs_one_unsaved_structured_call_on_the_judge_model(self, adapter):
        request = GroupFailuresApiInput.model_validate(_request())
        result = await group_failures(request)

        assert result.on_target_count == 2
        adapter.invoke.assert_awaited_once_with(
            input=grouping_input(request.spec_text, request.failures)
        )
        assert result.texts_shortened is False
        task, run_config, adapter_config = adapter.factory.call_args.args
        assert adapter_config.allow_saving is False
        assert task.instruction == GROUPING_INSTRUCTION
        assert json.loads(task.output_json_schema) == grouping_output_schema()
        assert run_config.model_name == "claude_sonnet_4_6"
        assert run_config.model_provider_name == ModelProviderName.anthropic
        assert run_config.thinking_level == "high"

    async def test_sends_the_spec_and_every_failure_as_evidence(self, adapter):
        request = GroupFailuresApiInput.model_validate(_request())
        sent = json.loads(grouping_input(request.spec_text, request.failures))
        assert sent["spec"] == SPEC
        assert [c["case_id"] for c in sent["failed_cases"]] == ["a", "b", "c"]
        assert sent["failed_cases"][0] == {
            "case_id": "a",
            "judge_reasoning": "It deleted without asking.",
            "case_excerpt": "First message: delete the old ones. Final reply: Done.",
            "expected_outcome": "The agent asks once, then deletes the 3 records.",
        }

    async def test_says_when_the_text_was_cut_to_fit(self, adapter):
        request = _request(tuple(f"case_{i}" for i in range(20)))
        for failure in request["failures"]:
            failure["judge_reasoning"] = "r" * 8000
        adapter.invoke = AsyncMock(
            return_value=Mock(
                output=Mock(
                    output=json.dumps(
                        _answer(
                            failures=[
                                {
                                    "case_id": "case_0",
                                    "group": "Dates shown in UTC",
                                    "evidence": ".",
                                }
                            ]
                        )
                    )
                )
            )
        )
        result = await group_failures(GroupFailuresApiInput.model_validate(request))
        assert result.texts_shortened is True
        sent = json.loads(adapter.invoke.call_args.kwargs["input"])
        assert len(sent["failed_cases"][0]["judge_reasoning"]) < 8000
        assert result.failure_count == 20
        assert sum(f.fault_kind == "unknown" for f in result.failures) == 19

    async def test_a_provider_error_becomes_a_grouping_error(self, adapter):
        adapter.invoke = AsyncMock(
            side_effect=KilnRunError(
                "An unexpected error occurred.",
                partial_trace=None,
                original=RuntimeError("rate limited"),
            )
        )
        with pytest.raises(FailureGroupingError, match="rate limited"):
            await group_failures(GroupFailuresApiInput.model_validate(_request()))

    async def test_an_answer_off_the_schema_becomes_a_grouping_error(self, adapter):
        adapter.invoke = AsyncMock(
            return_value=Mock(output=Mock(output='{"groups": "none"}'))
        )
        with pytest.raises(FailureGroupingError, match="did not match its schema"):
            await group_failures(GroupFailuresApiInput.model_validate(_request()))

    async def test_a_slow_call_times_out(self, adapter):
        adapter.invoke = AsyncMock(side_effect=TimeoutError())
        with pytest.raises(FailureGroupingError, match="took too long"):
            await group_failures(GroupFailuresApiInput.model_validate(_request()))


class TestGroupFailuresInput:
    def test_rejects_a_repeated_case_id(self):
        with pytest.raises(ValidationError, match="its own case_id"):
            GroupFailuresApiInput.model_validate(_request(("a", "a")))

    @pytest.mark.parametrize("count", [0, MAX_GROUPED_FAILURES + 1])
    def test_rejects_no_failures_and_too_many(self, count):
        with pytest.raises(ValidationError):
            GroupFailuresApiInput.model_validate(
                _request(tuple(f"case_{i}" for i in range(count)))
            )

    def test_rejects_unknown_fields(self):
        with pytest.raises(ValidationError):
            GroupFailuresApiInput.model_validate({**_request(), "extra": 1})


class TestGroupFailuresRoute:
    def test_returns_the_grouping(self, client, adapter):
        response = client.post(URL, json=_request())
        assert response.status_code == 200
        body = response.json()
        assert body["rule_summary"] == "Asks before deleting a record"
        assert body["on_target_count"] == 2
        assert body["groups"][0] == {
            "name": "Deleted without asking",
            "fault_kind": "agent",
            "about_rule": True,
            "count": 2,
            "example_case_id": "b",
            "example": "No confirm.",
        }
        assert body["texts_shortened"] is False

    def test_a_failed_grouping_answers_502_so_the_panel_can_degrade(
        self, client, adapter
    ):
        adapter.invoke = AsyncMock(side_effect=RuntimeError("provider down"))
        response = client.post(URL, json=_request())
        assert response.status_code == 502
        assert response.json()["message"]["code"] == "grouping_failed"
        assert "provider down" in response.json()["message"]["message"]

    def test_a_bad_request_never_calls_the_model(self, client, adapter):
        response = client.post(URL, json={**_request(), "failures": []})
        assert response.status_code == 422
        adapter.factory.assert_not_called()
