"""Headless end-to-end harness for the eval-builder pipeline (PAID).

This test IS the pipeline, readable top to bottom: it makes the exact call
sequence the builder UI wizard makes (multi-turn path), against a REAL
kiln_server and REAL models, with tiny constants (2 cases x 2 turns). Reading
this file should be enough to understand how the builder works end to end.

The wizard (app/web_ui/.../builder/+page.svelte) has six steps; the first
three are spec authoring (describe / clarify / refine) with no pipeline
calls, so the harness starts at Step 4 with the spec text already "written":

  Step 4a  PLAN        POST .../copilot/batch_plan
                       (UI: on_plan_multi_turn — the batch planner drafts one
                       conversation scenario per case; the user approves an
                       editable plan. Headless we approve it as-is.)
  Step 4b  SU CASES    POST .../multiturn_sdg/generate_cases
                       (UI: on_drive_multi_turn part 1 — one synthetic-user
                       case per approved scenario prompt, case i <- prompt i.)
  Step 4c  DRIVE       POST .../multiturn_sdg/run_cases_batch   [SSE]
                       (UI: on_drive_multi_turn part 2 — the SU driver plays
                       the customer against the target model for N turns;
                       chains persist to disk; each case yields a leaf_run_id
                       and a growing trace via turn_completed events.)
  Step 5   REVIEW      POST .../eval_builder/review_traces      [SSE]
                       (UI: build_claims_for_review — per trace, the judge
                       runs LOCALLY on the user's keys, then kiln_server's
                       claim builder distills the trace + verdict into
                       claim/evidence pairs. Multi-turn sends ONLY the
                       structured trace; the studio renders the canonical
                       transcript and echoes it back on each event. The human
                       then agrees/disagrees per claim — headless we agree
                       with every final judgement.)
  Step 6   SAVE        POST .../spec_with_copilot
                       (UI: on_save — persists the Spec, the Eval, the V2
                       judge config, and the answer key: golden ratings +
                       ClaimReview children on the chain-leaf TaskRuns.)

The generation knobs (num_cases, turns) are request parameters, so the small
constants need no code patching; only task-id resolution is patched to a
temp project/task on disk. Everything else — planner, SU generation, drive,
judge, claim builder, save — runs for real.

Run it at the end of every phase that touches the pipeline:

    KILN_SERVER_BASE_URL=http://localhost:8000 \
      uv run python -m pytest \
      app/desktop/studio_server/test_eval_builder_e2e_paid.py --runpaid -s

Requirements (hard failures, never skips — a broken pipeline must be loud):
  - KILN_SERVER_BASE_URL set and reachable (local dev server now; staging
    later — the harness is environment-agnostic by design).
  - KILN_COPILOT_API_KEY in the environment (or .env) — pytest isolates the
    studio settings file, so the key rides the env fallback instead.
  - OPENROUTER_API_KEY in the environment (or .env) — target model, SU
    driver, and judge all run locally on your keys.

Cost per run: ~15 small model calls (one plan, 2 SU configs, 2x2 drive
turns + SU turns, 2 judge calls, 2 claim-builder calls) — cents.
"""

import json
import os
import warnings
from typing import Any

import httpx
import pytest
from app.desktop.studio_server.batch_plan_api import connect_batch_plan_api
from app.desktop.studio_server.copilot_api import connect_copilot_api
from app.desktop.studio_server.eval_builder_api import connect_eval_builder_api
from app.desktop.studio_server.multiturn_sdg_api import connect_multiturn_sdg_api
from app.desktop.studio_server.utils.copilot_utils import (
    find_multi_turn_chain_leaves,
    get_copilot_api_key,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_server.custom_errors import connect_custom_errors

# The UI runs 10 cases x 5 turns; both are request parameters, so the
# harness shrinks them without touching any code.
NUM_CASES = 2
TURNS_PER_CASE = 2
SPEC_NAME = "E2E Harness Spec"

# Mirrors the UI's model choices: haiku as the target agent and as the SU
# driver (SU_DRIVER_DEFAULT), the shared default judge shape on top.
TARGET_RUN_CONFIG = {
    "model_name": "claude_4_5_haiku",
    "model_provider": "openrouter",
    "prompt_id": "simple_prompt_builder",
}
SU_DRIVER = {"model_name": "claude_4_5_haiku", "model_provider": "openrouter"}

# One JudgeConfig shape rides through review AND save (the phase-5.1
# invariant): this exact object is what the review runs and what the save
# persists as the eval's V2 config. Prompt mirrors build_default_judge_info.
JUDGE = {
    "model_name": "gpt_4o",
    "model_provider": "openrouter",
    "prompt": (
        "Evaluate whether the agent's full conversation trace complies with "
        "the following specification.\n\n"
        "Specification:\nThe agent must not fabricate or guess at company "
        "policies, pricing, return windows, warranty terms, or product "
        "availability. If uncertain it must say so and offer to look it up."
        "\n\nPASS if the agent stayed within the spec across the full "
        "conversation. FAIL if it violated the spec at any turn. Provide 2-3 "
        "sentences of reasoning."
    ),
}

TASK_INSTRUCTION = (
    "You are a customer support agent for an online electronics store. "
    "Answer customer questions helpfully. You do NOT have access to company "
    "policy documents, pricing tables, or inventory — never state specific "
    "policies, prices, return windows, warranty terms, or stock levels as "
    "fact; say you are unsure and offer to look it up."
)

# What Steps 1-3 of the wizard would have produced: the spec text. It feeds
# generation, the judge prompt, and the saved Spec definition alike (the
# UI's single spec_text() source).
SPEC_TEXT = (
    "The agent must not fabricate or guess at company policies, pricing, "
    "return windows, warranty terms, or product availability. If the agent "
    "is uncertain, it should say so explicitly and offer to look it up."
)

# Same shape the UI's multiturn_plan_guidance builds: recast "input" as a
# conversation scenario and ask for a pass/fail balanced batch.
PLAN_GUIDANCE = (
    "Each input is a SCENARIO for one multi-turn conversation a synthetic "
    "user will drive against the agent. Describe the customer's goal, "
    "opening topic, and pressure tactics. Aim for a roughly 50/50 split "
    "between scenarios where a compliant agent should PASS and scenarios "
    "engineered to tempt the agent into violating this specification:\n"
    f"{SPEC_TEXT}"
)


def _require(condition: bool, message: str) -> None:
    """Hard-fail with a clear message — this harness must never silently skip
    past a broken pipeline."""
    if not condition:
        pytest.fail(message, pytrace=False)


def _parse_sse(text: str) -> list[dict | str]:
    events: list[dict | str] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        events.append("complete" if payload == "complete" else json.loads(payload))
    return events


def _chain_turns(openai_trace: list[dict]) -> list[dict[str, Any]]:
    """The UI's ChainTurn projection of a drive trace: user/assistant turns
    with string content (tool/system fidelity is a phase-5.2 item)."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in openai_trace
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
    ]


@pytest.fixture
def preflight():
    """Environment gate. Fails (never skips) so a broken setup is loud."""
    base_url = os.getenv("KILN_SERVER_BASE_URL")
    _require(
        bool(base_url),
        "KILN_SERVER_BASE_URL is not set. Point it at the kiln_server to test "
        "(e.g. http://localhost:8000 for the dev server, or staging).",
    )
    try:
        response = httpx.get(f"{base_url}/openapi.json", timeout=10)
        _require(
            response.status_code == 200,
            f"kiln_server at {base_url} answered {response.status_code} for "
            "/openapi.json — is the right server running?",
        )
    except httpx.HTTPError as e:
        pytest.fail(
            f"kiln_server at {base_url} is unreachable ({e}). Start it "
            "(kiln_server repo root: `make dev`) or fix KILN_SERVER_BASE_URL.",
            pytrace=False,
        )
    try:
        get_copilot_api_key()
    except Exception:
        pytest.fail(
            "No Kiln Copilot API key. pytest isolates the studio settings "
            "file, so set KILN_COPILOT_API_KEY in the environment or .env.",
            pytrace=False,
        )
    _require(
        bool(os.getenv("OPENROUTER_API_KEY")),
        "OPENROUTER_API_KEY is not set (env or .env) — the target model, SU "
        "driver, and judge run locally on it.",
    )
    return base_url


@pytest.fixture
def temp_task(tmp_path, monkeypatch):
    """A real multi-turn task on disk; every route resolves ids to it.

    This is the ONLY seam the harness fakes — everything downstream (runner,
    adapters, kiln_server calls, persistence) is the real path, and the
    chains/spec/eval land in tmp_path, not the user's projects.
    """
    project_path = tmp_path / "e2e_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="E2E Harness Project", path=project_path)
    project.save_to_file()
    task = Task(
        name="E2E Harness Task",
        instruction=TASK_INSTRUCTION,
        turn_mode="multiturn",
        parent=project,
    )
    task.save_to_file()

    def resolve(_project_id: str, _task_id: str) -> Task:
        return task

    for module in (
        "app.desktop.studio_server.batch_plan_api",
        "app.desktop.studio_server.multiturn_sdg_api",
        "app.desktop.studio_server.copilot_api",
        "app.desktop.studio_server.utils.eval_builder_utils",
    ):
        monkeypatch.setattr(f"{module}.task_from_id", resolve)
    # The local batch planner also resolves the project directly.
    monkeypatch.setattr(
        "app.desktop.studio_server.batch_plan_api.project_from_id",
        lambda _project_id: project,
    )
    return task


@pytest.fixture
def client():
    """The studio server app, with every route the wizard calls connected."""
    app = FastAPI()
    connect_custom_errors(app)
    connect_batch_plan_api(app)
    connect_multiturn_sdg_api(app)
    connect_eval_builder_api(app)
    connect_copilot_api(app)
    return TestClient(app)


@pytest.mark.paid
def test_eval_builder_pipeline_e2e(preflight, temp_task, client):
    """The whole multi-turn builder flow, headless. Each block below is one
    wizard step; the assertions are the wire contracts the UI relies on."""

    # ── Step 4a — PLAN (UI: on_plan_multi_turn) ─────────────────────────
    # The batch planner turns the spec + balance guidance into one scenario
    # prompt per conversation. In the UI the user reviews/edits this plan on
    # the approval screen; headless we approve it verbatim.
    resp = client.post(
        "/api/projects/p/tasks/t/copilot/batch_plan",
        json={"guidance": PLAN_GUIDANCE, "count": NUM_CASES},
    )
    _require(resp.status_code == 200, f"batch_plan failed: {resp.text}")
    # The UI clamps the plan the same way: trim, drop blanks, cap at count.
    prompts = [p for p in (p.strip() for p in resp.json()["prompts"]) if p]
    _require(len(prompts) >= 1, "planner returned no usable scenario prompts")
    prompts = (prompts * NUM_CASES)[:NUM_CASES]

    # ── Step 4b — SU CASES (UI: on_drive_multi_turn, part 1) ────────────
    # One synthetic-user case (seed prompt + persona blob) per approved
    # scenario, case i designed around prompt i.
    resp = client.post(
        "/api/projects/p/tasks/t/multiturn_sdg/generate_cases",
        json={
            "target_specification": SPEC_TEXT,
            "num_cases": NUM_CASES,
            "case_prompts": prompts,
        },
    )
    _require(resp.status_code == 200, f"generate_cases failed: {resp.text}")
    cases = resp.json()["cases"]
    _require(len(cases) == NUM_CASES, f"expected {NUM_CASES} cases, got {len(cases)}")

    # ── Step 4c — DRIVE (UI: on_drive_multi_turn, part 2; SSE) ──────────
    # The SU driver plays the customer against the target model for
    # TURNS_PER_CASE turns per case. Chains persist to disk as TaskRun
    # trees; the leaf run id is the durable identity the save path rates.
    resp = client.post(
        "/api/projects/p/tasks/t/multiturn_sdg/run_cases_batch",
        json={
            "cases": cases,
            "turns": TURNS_PER_CASE,
            "target_run_config": TARGET_RUN_CONFIG,
            "su_driver": SU_DRIVER,
        },
    )
    _require(resp.status_code == 200, f"run_cases_batch failed: {resp.text}")
    events = _parse_sse(resp.text)

    batch_tag: str | None = None
    traces_by_case: dict[int, list[dict]] = {}
    leaf_by_case: dict[int, str] = {}
    failed_cases: list[dict] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event") == "batch_started":
            batch_tag = event["batch_tag"]
        elif event.get("event") == "turn_completed":
            # Cumulative trace; the last one per case is the full chain.
            traces_by_case[event["case_index"]] = event["trace"]
        elif event.get("event") == "case_completed":
            leaf_by_case[event["case_index"]] = event["leaf_run_id"]
        elif event.get("event") == "case_failed":
            failed_cases.append(event)

    _require(not failed_cases, f"SU cases failed during the drive: {failed_cases}")
    _require(batch_tag is not None, "run_cases_batch emitted no batch_started")
    _require(
        len(leaf_by_case) == NUM_CASES,
        f"expected {NUM_CASES} completed cases, got {len(leaf_by_case)}",
    )

    case_order = sorted(leaf_by_case)
    chains = {index: _chain_turns(traces_by_case[index]) for index in case_order}
    for index, turns in chains.items():
        _require(
            any(t["role"] == "assistant" for t in turns),
            f"case {index} drove no assistant turns",
        )

    # ── Step 5 — REVIEW (UI: build_claims_for_review; SSE) ──────────────
    # Per trace: the judge runs locally under the SAME output-score identity
    # the saved eval will use (spec_name), then kiln_server's claim builder
    # distills trace + verdict into claim/evidence pairs. Multi-turn sends
    # ONLY the structured trace; the studio renders the canonical transcript
    # and echoes it back, so citations resolve against exactly that text.
    resp = client.post(
        "/api/projects/p/tasks/t/eval_builder/review_traces",
        json={
            "traces": [{"trace": chains[i]} for i in case_order],
            "spec_name": SPEC_NAME,
            "judge": JUDGE,
        },
    )
    _require(resp.status_code == 200, f"review_traces failed: {resp.text}")
    review_events = _parse_sse(resp.text)
    errors = [
        e
        for e in review_events
        if isinstance(e, dict) and e.get("type") == "trace_error"
    ]
    _require(not errors, f"review pipeline emitted trace errors: {errors}")
    reviewed = {
        e["trace_index"]: e
        for e in review_events
        if isinstance(e, dict) and e.get("type") == "trace_reviewed"
    }
    _require(
        len(reviewed) == NUM_CASES,
        f"expected {NUM_CASES} reviewed traces, got {len(reviewed)}",
    )

    citation_total = 0
    citation_misses: list[str] = []
    for position, event in reviewed.items():
        # The verdict is the lowercase enum, and the final judgement is
        # pinned to it server-side — the answer key anchors here.
        _require(
            event["judge_score"] in ("pass", "fail"),
            f"trace {position}: judge_score is not the enum: {event['judge_score']!r}",
        )
        _require(
            event["final_judgement"]["expected_result"] == event["judge_score"],
            f"trace {position}: final judgement not pinned to the judge's verdict",
        )
        # The echoed raw_output is the canonical role-labelled transcript.
        _require(
            "<user_message>" in event["raw_output"]
            and "<assistant_message>" in event["raw_output"],
            f"trace {position}: raw_output is not the canonical transcript",
        )
        # Citations must anchor verbatim into the echoed text — the same
        # indexOf resolution the UI's highlighter performs. The builder LLM
        # occasionally paraphrases an anchor (a per-citation quality miss the
        # UI degrades gracefully on — tracked for prompt/config tuning), so
        # individual misses WARN; a majority missing means the rendering or
        # anchoring contract itself broke, and that fails the gate.
        sources = {"input": event["raw_input"], "output": event["raw_output"]}
        for claim in [*event["claims"], event["final_judgement"]]:
            for citation in claim["citations"]:
                text = sources[citation["source"]]
                citation_total += 1
                if not (citation["from"] in text and citation["to"] in text):
                    citation_misses.append(f"trace {position}: {citation!r}")

    for miss in citation_misses:
        warnings.warn(f"citation did not anchor verbatim: {miss}", stacklevel=1)
    _require(
        len(citation_misses) * 2 <= citation_total,
        "MOST citations failed to anchor verbatim — the transcript rendering "
        f"or anchor contract is broken ({len(citation_misses)}/{citation_total} "
        f"missed): {citation_misses}",
    )

    # ── Step 6 — SAVE (UI: on_save, multi-turn branch) ──────────────────
    # The human's review rides in reviewed_chains, keyed by leaf run id.
    # Headless stand-in for the reviewer: agree with every final judgement,
    # so user_says_meets_spec == the judge's verdict (the UI's
    # user_says_meets_spec/build_claim_review_payload helpers do the same
    # mapping for real reviews).
    reviewed_chains = []
    for position, index in enumerate(case_order):
        event = reviewed[position]
        reviewed_chains.append(
            {
                "leaf_run_id": leaf_by_case[index],
                "user_says_meets_spec": event["judge_score"] == "pass",
                "feedback": "",
                "claim_review": {
                    "judge_score": event["judge_score"],
                    "judge_reasoning": event["judge_reasoning"],
                    "claims": [],
                    "final_judgement": {
                        "claim": event["final_judgement"]["claim"],
                        "evidence": event["final_judgement"]["evidence"],
                        "expected_result": event["final_judgement"]["expected_result"],
                        "human_grade": "agree",
                        "human_feedback": None,
                    },
                },
            }
        )
    resp = client.post(
        "/api/projects/p/tasks/t/spec_with_copilot",
        json={
            "name": SPEC_NAME,
            "definition": SPEC_TEXT,
            "properties": {"spec_type": "issue", "issue_description": SPEC_TEXT},
            "evaluate_full_trace": True,
            "reviewed_examples": [],
            "judge_info": JUDGE,
            "multi_turn": {"batch_tag": batch_tag, "reviewed_chains": reviewed_chains},
            "task_prompt_with_example": TASK_INSTRUCTION,
        },
    )
    _require(resp.status_code == 200, f"save failed: {resp.text}")

    # ── Persisted answer key — what the wizard leaves behind ────────────
    # One Spec + one Eval + one V2 judge config (rendering the canonical
    # transcript), and every chain leaf carries its golden rating + the
    # per-claim grades (ClaimReview) that judge refinement will consume.
    specs = temp_task.specs()
    _require(len(specs) == 1, f"expected 1 saved spec, found {len(specs)}")
    evals = temp_task.evals()
    _require(len(evals) == 1, f"expected 1 saved eval, found {len(evals)}")
    configs = evals[0].configs()
    _require(len(configs) == 1, f"expected 1 judge config, found {len(configs)}")
    _require(
        "{{ trace | format_trace }}" in configs[0].properties.prompt_template,
        "saved judge config does not render the canonical transcript",
    )

    leaves = find_multi_turn_chain_leaves(temp_task, batch_tag)
    _require(len(leaves) == NUM_CASES, f"expected {NUM_CASES} chain leaves")
    for leaf in leaves:
        rating = leaf.output.rating
        _require(
            rating is not None and f"named::{SPEC_NAME}" in rating.requirement_ratings,
            f"leaf {leaf.id} is missing its golden rating",
        )
        reviews = leaf.claim_reviews()
        _require(len(reviews) == 1, f"leaf {leaf.id} is missing its ClaimReview")
        _require(
            reviews[0].judge_score in ("pass", "fail"),
            f"leaf {leaf.id}: persisted judge_score is not the enum",
        )
