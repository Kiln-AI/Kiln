"""Eval Builder review-pipeline helpers.

Two stages, run per trace by the orchestrator in eval_builder_api:
  - run_judge_for_trace  — LOCAL. Stubbed today; swaps to the Eval V2 llm_judge
    adapter when PR #1454 lands (see the `# POST-#1454` block).
  - build_claims_for_trace — REMOTE. Thin call to kiln_server's claim builder.

These are the only places that touch the (WIP) server/SDK shapes; they return
the stable UI-facing models so the endpoints and UI never see SDK types.
"""

from dataclasses import dataclass

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    build_claim_evidence_v1_copilot_build_claim_evidence_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    BuildClaimEvidenceInput,
    BuildClaimEvidenceOutput,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.api_models.eval_builder_models import (
    BuildClaimsApiOutput,
    ClaimApi,
    JudgeConfig,
)
from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key
from app.desktop.studio_server.utils.response_utils import unwrap_response
from fastapi import HTTPException


@dataclass
class JudgeVerdict:
    """A judge's decision for one trace, in the shape the claim builder wants."""

    judge_score: str
    judge_reasoning: str


async def run_judge_for_trace(
    project_id: str,
    task_id: str,
    raw_input: str,
    raw_output: str,
    judge: JudgeConfig,
) -> JudgeVerdict:
    """Run the candidate judge over one trace, LOCALLY.

    Returns a stringified verdict + reasoning for the claim builder.
    """
    # ── STUB (today) ────────────────────────────────────────────────────────
    # The real in-app judge lands with Eval V2 (PR #1454). Until then, synthesize
    # a deterministic verdict so the review surfaces a mix of pass/fail cases.
    # Deterministic on the trace so re-runs are stable. Ignores `judge`.
    fails = hash(raw_output) % 2 == 0
    return JudgeVerdict(
        judge_score="FAIL" if fails else "PASS",
        judge_reasoning=(
            "Placeholder verdict — the real in-app judge lands with Eval V2. "
            "This reasoning is not derived from the trace yet."
        ),
    )
    # ── POST-#1454 (swap ONLY this block) ─────────────────────────────────────
    # from kiln_ai.adapters.eval.registry import v2_eval_adapter_from_config
    # cfg = build_transient_llm_judge_config(
    #     judge.prompt, judge.model_name, judge.model_provider, output_scores=pass_fail
    # )
    # adapter = v2_eval_adapter_from_config(cfg)                       # local
    # result = await adapter.evaluate(EvalTaskInput(raw_input, raw_output))
    # return JudgeVerdict(
    #     judge_score=stringify(result.scores[score_key]),
    #     judge_reasoning=result.intermediate_outputs["reasoning"],
    # )


async def build_claims_for_trace(
    raw_input: str,
    raw_output: str,
    eval_rubric: str,
    judge_score: str,
    judge_reasoning: str,
) -> list[ClaimApi]:
    """Distill one trace + verdict into claim/evidence pairs via kiln_server.

    Thin remote passthrough: marshal → SDK call → map back. The claim generation
    (LLM) runs on kiln_server. Preserves the `from` citation alias for the UI.
    """
    api_key = get_copilot_api_key()
    client = get_authenticated_client(api_key)

    body = BuildClaimEvidenceInput.from_dict(
        {
            "raw_input": raw_input,
            "raw_output": raw_output,
            "eval_rubric": eval_rubric,
            "judge_reasoning": judge_reasoning,
            "judge_score": judge_score,
        }
    )

    detailed_result = await build_claim_evidence_v1_copilot_build_claim_evidence_post.asyncio_detailed(
        client=client,
        body=body,
    )
    result = unwrap_response(
        detailed_result,
        none_detail="Failed to build claims. Please try again.",
    )

    # result.to_dict() emits citations with the `from` key; CitationApi's alias
    # preserves it on the studio response (the UI greps that literal key).
    if isinstance(result, BuildClaimEvidenceOutput):
        return BuildClaimsApiOutput.model_validate(result.to_dict()).claims

    raise HTTPException(status_code=500, detail="Unknown error building claims.")
