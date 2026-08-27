# TODO(eval-v2): remove — this ENTIRE file is temporary ClaimDebug capture
# scaffolding, deleted before the v2 builder ships GA. It writes a sidecar
# record per successful build_claims so claim/citation data survives the
# browser tab during bug bash; nothing in the product reads these files.

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.utils.open_ai_types import (
    ChatCompletionMessageParam,
    materialize_lazy_content,
)
from kiln_server.task_api import task_from_id
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from app.desktop.studio_server._version import __version__
from app.desktop.studio_server.api_models.eval_builder_models import (
    BuildClaimsApiInput,
    BuildClaimsApiOutput,
    ClaimApi,
    ClaimDebugContext,
    FinalJudgementApi,
    JudgeScoreLiteral,
)

logger = logging.getLogger(__name__)

# Sidecar location under the task directory. Not a datamodel relationship
# folder, so the loader never scans it.
CAPTURE_DIR_NAME = "eval_debug"
CAPTURE_SUBDIR_NAME = "claim_builds"

# The run id comes off the wire and becomes part of a filename, so it must be a
# plain token. This keeps separators and ".." from escaping the capture
# directory, and keeps glob metacharacters out of the sibling-file scan below.
# Real ids are 12-digit integer strings; the wider set covers older id shapes.
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class ClaimDebug(BaseModel):
    """One build_claims round captured whole: the trace it ran on, the exact
    I/O and rubric the claim builder saw, the judge verdict, and the claims
    that came back. Self-contained so a record is analyzable on its own.

    Read a capture back with `model_validate(json.loads(text))`, the same way
    the datamodel loads runs: parsing straight from JSON resolves a message's
    string `content` to the content-parts branch of the union and fails.
    """

    schema_version: int = 1
    captured_at: datetime
    app_version: str
    source_run_id: str
    debug_context: ClaimDebugContext | None
    # Same type as TaskRun.trace. None when the run has no recorded trace or
    # the run could not be loaded; the I/O pair below is captured regardless.
    trace: list[ChatCompletionMessageParam] | None
    raw_input: str
    raw_output: str
    eval_rubric: str
    judge_score: JudgeScoreLiteral
    judge_reasoning: str
    claims: list[ClaimApi]
    final_judgement: FinalJudgementApi
    # kiln_server does not echo the builder's model or prompt version yet, so
    # these carry an honest placeholder rather than a guess.
    claim_builder_model: str = "not echoed"
    prompt_version: str = "not echoed"

    @model_validator(mode="after")
    def materialize_trace_content(self) -> Self:
        # Same treatment TaskRun gives its trace: pydantic validates the
        # message wrappers' `content` into a single-use lazy iterator, so
        # materialize it or a parsed record's trace is unreadable twice.
        if self.trace is not None:
            materialize_lazy_content(self.trace)
        return self


def _next_capture_path(capture_dir: Path, source_run_id: str) -> Path:
    """Next free `{run_id}_{n}.json` in the directory, counting past whatever
    is already there. Refine-round rebuilds append instead of overwriting, so
    the history of a trace's claim builds is preserved.
    """
    highest = 0
    for existing in capture_dir.glob(f"{source_run_id}_*.json"):
        suffix = existing.stem[len(source_run_id) + 1 :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return capture_dir / f"{source_run_id}_{highest + 1}.json"


def capture_claim_debug(
    project_id: str,
    task_id: str,
    input: BuildClaimsApiInput,
    output: BuildClaimsApiOutput,
) -> None:
    """Write one ClaimDebug sidecar for a completed build_claims call.

    Fail-open by contract: every failure here (task load, run load, disk,
    serialization) is swallowed and logged. Debug capture must never turn a
    successful claim build into a failed request.
    """
    try:
        source_run_id = input.source_run_id
        if source_run_id is None:
            # Old clients don't send a run id; without one there is nothing to
            # key the capture to, so skip silently.
            return
        if not SAFE_RUN_ID.match(source_run_id):
            # Skip rather than sanitize: an id this shape names no real run, so
            # there is nothing worth capturing under a cleaned-up name.
            logger.warning(
                "ClaimDebug capture skipped, unusable run id: %r", source_run_id
            )
            return

        task = task_from_id(project_id, task_id)
        if task.path is None:
            # An unsaved task has no directory to write the sidecar into.
            return

        # One code path for both arms: a multi-turn leaf's trace is already the
        # cumulative conversation and a single-turn run's is its one exchange.
        run = TaskRun.from_id_and_parent_path(source_run_id, task.path)
        trace = run.trace if run is not None else None

        record = ClaimDebug(
            captured_at=datetime.now(timezone.utc),
            app_version=__version__,
            source_run_id=source_run_id,
            debug_context=input.debug_context,
            trace=trace,
            raw_input=input.raw_input,
            raw_output=input.raw_output,
            eval_rubric=input.eval_rubric,
            judge_score=input.judge_score,
            judge_reasoning=input.judge_reasoning,
            claims=output.claims,
            final_judgement=output.final_judgement,
        )

        capture_dir = task.path.parent / CAPTURE_DIR_NAME / CAPTURE_SUBDIR_NAME
        capture_dir.mkdir(parents=True, exist_ok=True)
        # by_alias keeps citations' `from` key, matching the wire shape.
        _next_capture_path(capture_dir, source_run_id).write_text(
            record.model_dump_json(by_alias=True, indent=2)
        )
    except Exception as e:
        logger.warning("ClaimDebug capture failed, ignoring: %s", e)
