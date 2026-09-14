from __future__ import annotations

import json
from dataclasses import replace

import pytest

from .conftest import cell, decision_record, paired_cell
from .cost import CostLine, CostModel
from .faults import FaultResult
from .metrics import (
    Gate,
    GateThresholds,
    config_scores,
    decision_stat,
    evaluate_gates,
    near_neighbour,
    pair_cells,
    paired_delta,
    rank_stat,
    sanity_counts,
)
from .replay import Mismatch
from .report import (
    ALL_STEPS,
    Deviation,
    RunMeta,
    build_report,
    render_markdown,
    write_report,
)
from .scrub import Diff

META = RunMeta(
    run_id="run-2026-03-04",
    started_at="2026-03-04T00:00:00Z",
    finished_at="2026-03-04T04:00:00Z",
    world_version="notes@eng1:abc",
    fixture_id="notes-v1",
    fixture_exported_at="2026-03-01T00:00:00Z",
    fixture_age_days=3,
    allow_stale=False,
    reference_version="reference@1.4.2",
    model_ids={"A": "strong", "B": "small"},
    repeats=3,
    input_pairs=20,
    inputs=40,
    configurations=["A", "B"],
    halves=["tuning"],
    sealed_world_version=None,
    sealed_voided=False,
    decision_temperature=0.0,
    world_ports={"clean": 8010},
    reset_seconds=[11.5],
    observed_429s=0,
    deviations=[
        Deviation(
            date="2026-03-04",
            item="decision temperature",
            reasoning="temperature 0 so arm noise is model-side minimal",
        )
    ],
)

COST = CostModel(
    lines=[
        CostLine("real_episodes", 120, 1.5, 1.4, "6 configurations, sequential"),
        CostLine("judge_calls", 1200, 0.0, None, "no model cost"),
    ],
    total_estimate_usd=1.5,
    total_observed_usd=1.4,
    pricing_source="config",
)

MISMATCH = Mismatch(
    run_id="run-1",
    configuration="A",
    step_index=4,
    tool_name="list_notes",
    arguments={"page": 1},
    recorded={"count": 100},
    replayed={"count": 20},
    diffs=[Diff("/count", 100, 20)],
    kind="mismatch",
    declared=(),
    classes=(("list_notes", "/count"),),
)

FAULT = FaultResult(
    fault="page_size",
    target="replay",
    port=8011,
    world_version="notes@1+fault.page_size",
    triggers=340,
    gates=[],
    moved=["replay"],
    statistic_moved=False,
    detected=True,
    inconclusive=False,
)


def full_inputs():
    paired = [
        paired_cell(name, n, 1, real=n <= rate, world=n <= rate)
        for name, rate in (("A", 9), ("B", 4))
        for n in range(1, 11)
    ]
    laid_out = [
        cell(p.configuration, p.input_no, p.repeat, system, passed=True)
        for p in paired
        for system in ("real", "world")
    ]
    scores = config_scores(laid_out, paired, min_valid=1) + config_scores(
        laid_out, paired, min_valid=1, by_half=True
    )
    decisions = [
        decision_record(f"run-{n}", 0, arm, prefix="divergent", agree=True)
        for n in range(6)
        for arm in ("world", "control")
    ]
    dropped = pair_cells(laid_out)[1]
    gates = evaluate_gates(
        mismatches=[MISMATCH],
        paired=paired,
        scores=config_scores(laid_out, paired, min_valid=1),
        decisions=decisions,
        thresholds=GateThresholds(),
        replay_steps=100,
    )
    return dict(
        gates=gates,
        cells=laid_out,
        paired=paired,
        dropped=dropped,
        scores=scores,
        paired_stat=paired_delta(paired, resamples=100),
        rank=rank_stat(paired, spearman_min=0.8, resamples=100),
        near=near_neighbour(paired, a="A", f="B", resamples=100),
        decision=decision_stat(decisions),
        sanity=sanity_counts(laid_out, dropped),
        mismatches=[MISMATCH],
        caveats=["3 recorded steps carried transport error codes"],
        faults=[FAULT],
        cost=COST,
        replay_steps=100,
        decision_records=len(decisions),
    )


def test_build_report_schema_version_and_keys():
    report = build_report(META, executed_steps=list(ALL_STEPS), **full_inputs())
    assert report["schema_version"] == 2
    for key in (
        "meta",
        "executed_steps",
        "complete",
        "gates",
        "cells",
        "pairs",
        "scores",
        "scores_by_half",
        "near_neighbour",
        "tie_band",
        "ties",
        "replay",
        "decision",
        "sanity",
        "faults",
        "cost",
        "caveats",
        "decision_rules",
        "what_this_does_not_prove",
    ):
        assert key in report, key
    assert report["meta"]["run_id"] == "run-2026-03-04"
    assert report["pairs"]["kept"] == 20
    assert report["replay"]["steps"] == 100
    assert report["replay"]["ok"] == 99
    assert report["replay"]["undeclared_classes"] == [["list_notes", "/count"]]
    assert report["decision"]["records"] == 12
    assert [s["half"] for s in report["scores"]] == [None, None, None, None]
    assert all(s["half"] is not None for s in report["scores_by_half"])
    # the whole object must survive a JSON round trip
    assert json.loads(json.dumps(report))["complete"] is True


def test_build_report_complete_only_when_all_steps():
    inputs = full_inputs()
    inputs["gates"] = [g for g in inputs["gates"] if g.name in ("replay", "paired")]
    partial = build_report(META, executed_steps=["real", "world", "replay"], **inputs)
    assert partial["complete"] is False
    full = build_report(META, executed_steps=list(ALL_STEPS), **full_inputs())
    assert full["complete"] is True


def test_build_report_refuses_a_gate_whose_step_did_not_run():
    """The one place that can see both the gate list and the step list, and so the one
    place that can catch a driver whose two disagree."""
    with pytest.raises(ValueError, match="step 'decision' is not in executed_steps"):
        build_report(META, executed_steps=["real", "world", "replay"], **full_inputs())


def test_build_report_skipped_step_gates_null():
    gates = evaluate_gates(
        mismatches=None,
        paired=None,
        scores=None,
        decisions=None,
        thresholds=GateThresholds(),
        replay_steps=None,
    )
    report = build_report(
        META,
        executed_steps=["real"],
        gates=gates,
        cells=[],
        paired=[],
        dropped=[],
        scores=[],
        paired_stat=None,
        rank=None,
        near=None,
        decision=None,
        sanity=sanity_counts([], []),
        mismatches=[],
        caveats=[],
        faults=[],
        cost=COST,
    )
    assert report["complete"] is False
    assert all(gate["value"] is None for gate in report["gates"])
    assert all(gate["passed"] is None for gate in report["gates"])
    assert all(gate["outcome"] == "skipped" for gate in report["gates"])
    assert report["decision"] is None
    assert report["near_neighbour"] is None
    rendered = render_markdown(report)
    assert "The fault step did not run." in rendered
    assert "| replay | — | — |" in rendered


def test_render_markdown_contains_gate_table_rules_and_not_proven():
    report = build_report(META, executed_steps=list(ALL_STEPS), **full_inputs())
    rendered = render_markdown(report)
    assert "# Validity report: run-2026-03-04" in rendered
    assert "## Gates" in rendered
    assert "## Failure decision rules" in rendered
    assert "thesis at risk; escalate before fixing" in rendered
    assert "## What this does not prove" in rendered
    assert "- generated worlds" in rendered
    assert "## Near neighbour" in rendered
    assert "## Tie band" in rendered
    assert "## Replay" in rendered
    assert "### list_notes" in rendered
    assert "## Decision replay" in rendered
    assert "## Sanity counts" in rendered
    assert "## Faults" in rendered
    assert "page_size" in rendered
    assert "340" in rendered
    assert "## Cost" in rendered
    assert "## Caveats" in rendered
    assert "transport error codes" in rendered
    assert "## Deviations" in rendered
    assert "temperature 0 so arm noise is model-side minimal" in rendered
    assert "## Run metadata" in rendered
    assert "notes-v1 exported 2026-03-01T00:00:00Z" in rendered


def test_render_markdown_per_half_tables():
    report = build_report(META, executed_steps=list(ALL_STEPS), **full_inputs())
    rendered = render_markdown(report)
    assert "## Per-configuration scores (combined)" in rendered
    assert "## Per-configuration scores (by half)" in rendered
    assert "| A | real | all |" in rendered
    assert "| A | real | tuning |" in rendered


def test_write_report_writes_both_files(tmp_path):
    report = build_report(META, executed_steps=list(ALL_STEPS), **full_inputs())
    json_path, md_path = write_report(report, tmp_path / "report")
    assert json_path.name == "validity.json" and md_path.name == "validity.md"
    assert json.loads(json_path.read_text())["schema_version"] == 2
    assert md_path.read_text().startswith("# Validity report")


def test_build_report_tolerates_a_gate_with_no_interval():
    gate = Gate(
        name="replay",
        value=0.0,
        threshold=0.0,
        passed=True,
        outcome="passed",
        interval=None,
        inputs={"steps": 100},
        reason=None,
    )
    inputs = full_inputs()
    inputs["gates"] = [gate]
    report = build_report(META, executed_steps=list(ALL_STEPS), **inputs)
    assert report["gates"][0]["interval"] is None
    assert "| replay | 0.000 | 0.000 | — | passed |" in render_markdown(report)


@pytest.mark.parametrize("steps", [[], ["report"]])
def test_build_report_handles_any_executed_step_list(steps):
    inputs = full_inputs()
    inputs["gates"] = []
    report = build_report(META, executed_steps=steps, **inputs)
    assert report["complete"] is False
    render_markdown(report)


def test_build_report_does_not_invent_replay_counts():
    """A step count nobody supplied is unknown. Guessing `len(mismatches)` would publish
    "0 matching steps" for a clean replay."""
    inputs = full_inputs()
    inputs.pop("replay_steps")
    inputs["mismatches"] = []
    inputs["gates"] = evaluate_gates(
        mismatches=[],
        paired=None,
        scores=None,
        decisions=None,
        thresholds=GateThresholds(),
        replay_steps=None,
    )[:1]
    report = build_report(META, executed_steps=list(ALL_STEPS), **inputs)
    assert report["replay"]["steps"] is None
    assert report["replay"]["ok"] is None


def test_build_report_refuses_a_replay_count_the_gate_did_not_use():
    """Publishing "100 steps replayed" beside a gate that says "no replayed steps" is the
    same class of disagreement `_check_gates` exists to catch."""
    inputs = full_inputs()
    inputs["replay_steps"] = 999
    with pytest.raises(
        ValueError, match="judged on 100 steps but the report was given"
    ):
        build_report(META, executed_steps=list(ALL_STEPS), **inputs)


def test_build_report_refuses_more_mismatches_than_steps():
    inputs = full_inputs()
    inputs["replay_steps"] = 0
    inputs["gates"] = [
        replace(g, inputs={**g.inputs, "steps": 0}) if g.name == "replay" else g
        for g in inputs["gates"]
    ]
    with pytest.raises(ValueError, match="cannot be"):
        build_report(META, executed_steps=list(ALL_STEPS), **inputs)


def test_build_report_refuses_a_gate_it_cannot_place():
    inputs = full_inputs()
    inputs["gates"] = [replace(inputs["gates"][0], name="mystery")]
    with pytest.raises(ValueError, match="not one this report knows how to place"):
        build_report(META, executed_steps=list(ALL_STEPS), **inputs)


def test_build_report_writes_non_finite_floats_as_null():
    """json.dumps writes bare NaN, which is not JSON and which the regrade step, reading
    this file back, would reject."""
    inputs = full_inputs()
    inputs["paired_stat"] = replace(inputs["paired_stat"], delta=float("nan"))
    report = build_report(META, executed_steps=list(ALL_STEPS), **inputs)
    assert report["paired"]["delta"] is None
    json.loads(json.dumps(report))


def test_render_markdown_escapes_a_pipe_in_a_value():
    inputs = full_inputs()
    inputs["caveats"] = ["a | b"]
    rendered = render_markdown(
        build_report(META, executed_steps=list(ALL_STEPS), **inputs)
    )
    assert "- a | b" in rendered
    inputs["faults"] = [replace(FAULT, fault="a|b")]
    rendered = render_markdown(
        build_report(META, executed_steps=list(ALL_STEPS), **inputs)
    )
    row = next(line for line in rendered.splitlines() if "a\\|b" in line)
    # nine bars for eight columns; the escaped one does not open a ninth
    assert row.count("|") - row.count("\\|") == 9


def test_render_markdown_explains_unscored_episodes():
    inputs = full_inputs()
    laid_out = [
        cell("A", 1, 1, "real", passed=None),
        cell("A", 1, 1, "world"),
    ]
    dropped = pair_cells(laid_out)[1]
    inputs["cells"] = laid_out
    inputs["sanity"] = sanity_counts(laid_out, dropped)
    rendered = render_markdown(
        build_report(META, executed_steps=list(ALL_STEPS), **inputs)
    )
    assert "no judge traceback was written for them" in rendered
