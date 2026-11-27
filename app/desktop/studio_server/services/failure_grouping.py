"""Sorting a judged Eval Builder batch's failed cases by cause, for the eval check
panel. One structured-output call on the judge's model, run locally with the user's
keys."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, get_args

from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import (
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.retry_classification import unwrap_kiln_run_error
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task
from pydantic import BaseModel, Field, ValidationError

from app.desktop.studio_server.api_models.eval_builder_models import (
    FailedCaseApi,
    FailureGroupApi,
    FailureLabelApi,
    FaultKind,
    GroupFailuresApiInput,
    GroupFailuresApiOutput,
    JudgeConfig,
)

logger = logging.getLogger(__name__)

GROUPING_TIMEOUT_SECONDS = 300

# The failed cases' text sent to the model, in characters (about 20,000 tokens), so a
# full batch fits a 128k-context judge model with room for the answer. Above it, every
# text is cut in the middle by the same ratio, down to MIN_CLIPPED_CHARS.
MAX_GROUPING_INPUT_CHARS = 80_000
MIN_CLIPPED_CHARS = 200

# Groups longer than this are cut for the panel's table, not rejected.
MAX_GROUP_NAME_CHARS = 120

# The group a case lands in when the answer gives it no usable label.
UNLABELLED_GROUP = "Not labelled by the grouping"

GROUPING_INSTRUCTION = """\
You sort the failed cases of an eval by cause. Every case you get has already failed. Do not judge it again.

The eval checks one behaviour of an AI agent. The spec says what that behaviour is. Each failed case comes with the judge's reasoning for its FAIL verdict, a short excerpt of the case, and, on some cases, the expected outcome the judge graded against.

1. For each failed case, decide who caused the failure. Use exactly one fault kind:
- agent: the agent under test did something wrong. This is the only kind that measures the agent.
- reference: the expected outcome is wrong, incomplete, or stricter than the spec, so a correct agent would also fail.
- judge: the judge misread the case, or failed the agent for a rule that is in neither the spec nor the expected outcome.
- world: the environment or its data was broken (a tool error the agent could not avoid, records that are missing or contradict each other).
- simulated_user: the simulated user left its script, gave the agent wrong facts, or pushed the agent into the failure.
- unknown: the evidence is not enough to decide. Use it when the judge's reasoning is empty, cut off, or only repeats the verdict.

2. Put the failures into cause groups. A group name says what went wrong in plain words, in at most 8 words, for example "Deleted records without asking first". Failures with the same cause share a group, and every group has one fault kind. Use as few groups as the evidence supports. Do not make one group per case unless every cause is different.

3. For each group, set about_rule. It is true only when the spec text itself asks for or forbids the behaviour that failed. A failure about something the spec does not mention (for example a date format, the tone of a reply, or a rule from the agent's own instructions) is not about the rule, even when the judge failed the case for it.

Rules:
- Classify only from the evidence you are given. Do not guess what happened outside it.
- Never invent a rule. A rule is in the spec only when the spec text says it.
- For each failure, write evidence: one sentence that quotes or closely restates the part of the judge's reasoning or the case excerpt that shows the cause. For an unknown case, say what is missing.
- Write rule_summary: the behaviour the spec measures, in at most 15 words, in the spec's own words where you can.
- List every failed case exactly once in failures, with its case_id unchanged, and name a group from your groups list.
"""


class FailureGroupingError(Exception):
    """The grouping call failed, or its answer could not be used."""


class GroupingAnswerGroup(BaseModel):
    """One cause group as the model defines it."""

    name: str = Field(min_length=1)
    fault_kind: FaultKind
    about_rule: bool


class GroupingAnswerLabel(BaseModel):
    """One failed case's group, as the model assigns it."""

    case_id: str
    group: str
    evidence: str


class GroupingAnswer(BaseModel):
    """The model's answer, in the shape of grouping_output_schema()."""

    rule_summary: str = Field(min_length=1)
    groups: list[GroupingAnswerGroup]
    failures: list[GroupingAnswerLabel]


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    # Strict structured output needs every property required and the object closed.
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def grouping_output_schema() -> dict[str, Any]:
    """The JSON schema of the model's answer, with no `$ref`, so it holds under
    strict structured output."""
    group = _object_schema(
        {
            "name": {"type": "string", "description": "What went wrong."},
            "fault_kind": {
                "type": "string",
                "enum": list(get_args(FaultKind)),
            },
            "about_rule": {"type": "boolean"},
        }
    )
    label = _object_schema(
        {
            "case_id": {"type": "string"},
            "group": {"type": "string", "description": "A name from groups."},
            "evidence": {"type": "string"},
        }
    )
    return _object_schema(
        {
            "rule_summary": {"type": "string"},
            "groups": {"type": "array", "items": group},
            "failures": {"type": "array", "items": label},
        }
    )


def clip_middle(text: str, max_chars: int) -> str:
    """Cut the middle out of a long text: a judge's reasoning tends to open with what
    it checked and close with its verdict, and both matter."""
    if len(text) <= max_chars:
        return text
    half = max(0, (max_chars - 5) // 2)
    return f"{text[:half]} […] {text[len(text) - half :]}"


def fit_to_budget(
    failures: list[FailedCaseApi],
) -> tuple[list[FailedCaseApi], bool]:
    """The failures with their text cut to fit MAX_GROUPING_INPUT_CHARS, and whether
    any text was cut."""
    texts = [
        text
        for f in failures
        for text in (f.judge_reasoning, f.case_summary, f.judge_guidance or "")
    ]
    total = sum(len(text) for text in texts)
    if total <= MAX_GROUPING_INPUT_CHARS:
        return failures, False
    # Texts at or under the floor are never cut, so only the rest share the cut.
    short = sum(len(text) for text in texts if len(text) <= MIN_CLIPPED_CHARS)
    ratio = max(0.0, MAX_GROUPING_INPUT_CHARS - short) / (total - short)

    def fit(text: str) -> str:
        return clip_middle(text, max(MIN_CLIPPED_CHARS, int(len(text) * ratio)))

    return [
        f.model_copy(
            update={
                "judge_reasoning": fit(f.judge_reasoning),
                "case_summary": fit(f.case_summary),
                "judge_guidance": fit(f.judge_guidance) if f.judge_guidance else None,
            }
        )
        for f in failures
    ], True


def grouping_input(spec_text: str, failures: list[FailedCaseApi]) -> str:
    """The user message: the spec and the failed cases, as JSON."""
    return json.dumps(
        {
            "spec": spec_text,
            "failed_cases": [
                {
                    "case_id": failure.case_id,
                    "judge_reasoning": failure.judge_reasoning,
                    "case_excerpt": failure.case_summary,
                    "expected_outcome": failure.judge_guidance,
                }
                for failure in failures
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def _grouping_adapter(judge: JudgeConfig):
    task = Task(
        name="failure_grouping",
        description="In-memory failure grouping for the eval check panel. Not persisted.",
        instruction=GROUPING_INSTRUCTION,
        output_json_schema=json.dumps(grouping_output_schema()),
    )
    run_config = KilnAgentRunConfigProperties(
        model_name=judge.model_name,
        model_provider_name=judge.model_provider,
        prompt_id=PromptGenerators.SIMPLE,
        structured_output_mode=default_structured_output_mode_for_model_provider(
            judge.model_name,
            judge.model_provider,
            default=StructuredOutputMode.json_schema,
        ),
        thinking_level=judge.thinking_level,
    )
    return adapter_for_task(task, run_config, AdapterConfig(allow_saving=False))


async def group_failures(request: GroupFailuresApiInput) -> GroupFailuresApiOutput:
    """Sort the failed cases by cause. Raises FailureGroupingError when the call
    fails, times out, or returns an answer that labels none of the cases."""
    adapter = _grouping_adapter(request.judge)
    failures, texts_shortened = fit_to_budget(request.failures)
    try:
        run = await asyncio.wait_for(
            adapter.invoke(input=grouping_input(request.spec_text, failures)),
            timeout=GROUPING_TIMEOUT_SECONDS,
        )
    except TimeoutError as e:
        raise FailureGroupingError("The grouping call took too long.") from e
    except Exception as e:
        logger.warning("Failure grouping call failed", exc_info=True)
        raise FailureGroupingError(
            f"The grouping call failed: {unwrap_kiln_run_error(e)}"
        ) from e
    try:
        answer = GroupingAnswer.model_validate_json(run.output.output)
    except ValidationError as e:
        raise FailureGroupingError(
            "The grouping answer did not match its schema."
        ) from e
    return summarize_answer(
        answer,
        [failure.case_id for failure in request.failures],
        texts_shortened=texts_shortened,
    )


def _label(
    case_id: str,
    label: GroupingAnswerLabel | None,
    groups: dict[str, GroupingAnswerGroup],
) -> FailureLabelApi:
    if label is None:
        return FailureLabelApi(
            case_id=case_id,
            fault_kind="unknown",
            group=UNLABELLED_GROUP,
            about_rule=False,
            evidence="The grouping answer did not label this case.",
        )
    group = groups[label.group]
    return FailureLabelApi(
        case_id=case_id,
        fault_kind=group.fault_kind,
        group=label.group[:MAX_GROUP_NAME_CHARS],
        about_rule=group.about_rule,
        evidence=label.evidence,
    )


def summarize_answer(
    answer: GroupingAnswer, case_ids: list[str], texts_shortened: bool = False
) -> GroupFailuresApiOutput:
    """The response from a model answer: labels in the request's case order, groups
    counted here rather than trusted from the model, largest first.

    One bad label does not spoil the rest. A case the answer leaves out, or labels
    only with an undefined group, lands in UNLABELLED_GROUP as `unknown`; a label for a
    case id not in the request is ignored. The first definition of a group name, and
    the first usable label of a case, win. An answer that labels no case is an error."""
    groups: dict[str, GroupingAnswerGroup] = {}
    for group in answer.groups:
        groups.setdefault(group.name, group)
    wanted = set(case_ids)
    labels: dict[str, GroupingAnswerLabel] = {}
    for label in answer.failures:
        if label.case_id in wanted and label.group in groups:
            labels.setdefault(label.case_id, label)
    if not labels:
        raise FailureGroupingError("The grouping answer labelled none of the cases.")

    failures = [_label(case_id, labels.get(case_id), groups) for case_id in case_ids]
    kinds: dict[str, tuple[FaultKind, bool]] = {}
    for name, group in groups.items():
        kinds.setdefault(
            name[:MAX_GROUP_NAME_CHARS], (group.fault_kind, group.about_rule)
        )
    kinds.setdefault(UNLABELLED_GROUP, ("unknown", False))
    members: dict[str, list[FailureLabelApi]] = {}
    for failure in failures:
        members.setdefault(failure.group, []).append(failure)
    # Python's sort is stable, so equal counts keep the order of first appearance.
    ordered = sorted(members.items(), key=lambda item: -len(item[1]))
    return GroupFailuresApiOutput(
        rule_summary=answer.rule_summary,
        failures=failures,
        groups=[
            FailureGroupApi(
                name=name,
                fault_kind=kinds[name][0],
                about_rule=kinds[name][1],
                count=len(cases),
                example_case_id=cases[0].case_id,
                example=cases[0].evidence,
            )
            for name, cases in ordered
        ],
        on_target_count=sum(
            1 for f in failures if f.fault_kind == "agent" and f.about_rule
        ),
        failure_count=len(failures),
        texts_shortened=texts_shortened,
    )
