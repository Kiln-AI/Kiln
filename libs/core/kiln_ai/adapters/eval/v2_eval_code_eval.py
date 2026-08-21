"""V2 adapter for code_eval: runs user-authored Python scorer in a sandboxed subprocess."""

<<<<<<< HEAD
import math
=======
>>>>>>> 721c4941b
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable

from kiln_ai.adapters.eval.base_eval import BaseEval, BaseV2EvalBridge

if TYPE_CHECKING:
    from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
    from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.adapters.eval.sandbox_worker import execute_scorer_bridged
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    EvalConfig,
    EvalScores,
    EvalTaskInput,
    SkippedReason,
    V2EvalResult,
)
<<<<<<< HEAD
from kiln_ai.run_context import get_eval_input_id
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.sandbox_bridge import NestedToolServer, run_bridged_child
=======
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.sandbox_bridge import (
    NestedToolServer,
    ToolCallLogEntry,
    run_bridged_child,
)
>>>>>>> 721c4941b

_trust_lock = Lock()
_trusted_projects: set[str] = set()

<<<<<<< HEAD
# A scorer may return exactly {SKIP_SENTINEL_KEY: "<reason>"} instead of scores
# to record the run as skipped (not applicable). Skipped runs count as complete
# but are excluded from score aggregates, so a self-gating eval's mean becomes
# its rate over applicable runs rather than being diluted by clean-or-NA 1.0s.
SKIP_SENTINEL_KEY = "__skipped__"

=======
>>>>>>> 721c4941b

def add_code_trust(project_path: str) -> None:
    """Confer code trust on a project for the current session.

    Called when NEW/not-yet-saved code is admitted or executed (saving a code
    tool/eval, running not-yet-saved code in a test pane). Saved code is
    trusted to run without this — the flag governs the authoring session only.
    """
    with _trust_lock:
        _trusted_projects.add(project_path)


def has_add_code_trust(project_path: str) -> bool:
    with _trust_lock:
        return project_path in _trusted_projects


def _reset_add_code_trust() -> None:
    """Test-only reset of the in-memory trust set. Not part of the product API."""
    with _trust_lock:
        _trusted_projects.clear()


class CodeEvalAdapter(BaseV2EvalBridge):
    """V2 adapter that executes user-authored Python scorer code in a subprocess."""

    def __init__(
        self,
        eval_config: EvalConfig,
        run_config: "RunConfigProperties | None" = None,
        skills: "SkillsDict | None" = None,
    ) -> None:
        super().__init__(eval_config, run_config, skills)
        assert isinstance(self.properties, CodeEvalProperties)

        # Set by the test-pane endpoint, which is the one place a code judge's
        # nested tool calls (including LLM calls, which cost money) have somewhere
        # to be shown: the author is iterating on the code right there. An eval run
        # leaves it None -- per-item logs have no home in the run UI yet.
        self.tool_call_recorder: Callable[[ToolCallLogEntry], None] | None = None

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        props = self.properties
        assert isinstance(props, CodeEvalProperties)

        inputs: dict[str, Any] = {
            "output": eval_input.final_message,
            "trace": eval_input.trace,
            "reference_data": eval_input.reference_data,
            "task_input": eval_input.task_input,
        }

        server = NestedToolServer(
            allowlist=props.tool_allowlist,
            project=self.target_task.parent_project(),
            task=self.target_task,
            context=ToolCallContext(
                allow_saving=False,
<<<<<<< HEAD
                eval_input_id=get_eval_input_id(),
=======
>>>>>>> 721c4941b
                eval_output_schema=BaseEval.build_score_schema(
                    self.eval, allow_float_scores=False
                ),
            ),
<<<<<<< HEAD
            recorder=None,
=======
            recorder=self.tool_call_recorder,
>>>>>>> 721c4941b
        )

        res = await run_bridged_child(
            target=execute_scorer_bridged,
            args=(props.code, inputs),
            timeout_s=float(props.timeout_seconds),
            server=server,
        )

        if res.timed_out:
            raise RuntimeError(
                f"Code eval scorer timed out after {props.timeout_seconds}s"
            )
        if res.crashed:
<<<<<<< HEAD
            raise RuntimeError(f"Scorer crashed (exit code {res.exit_code})")
=======
            raise RuntimeError(res.crash_description("Scorer"))
>>>>>>> 721c4941b

        result_msg = res.result_msg
        assert result_msg is not None
        if "error" in result_msg:
            raise RuntimeError(
                f"Code eval scorer failed: {result_msg['error']}\n"
                f"{result_msg.get('traceback', '')}"
            )

        raw_scores = result_msg["ok"]
        if not isinstance(raw_scores, dict):
            raise RuntimeError(
                f"Scorer must return a dict, got {type(raw_scores).__name__}"
            )

        if set(raw_scores.keys()) == {SKIP_SENTINEL_KEY}:
            detail = raw_scores[SKIP_SENTINEL_KEY]
            if not isinstance(detail, str) or not detail:
                raise RuntimeError(
                    f"{SKIP_SENTINEL_KEY} must carry a non-empty reason string, "
                    f"got {detail!r}"
                )
            return V2EvalResult(
                skipped_reason=SkippedReason.not_applicable,
                skipped_detail=detail,
            )

        scores = self._validate_scores(raw_scores)
        return V2EvalResult(scores=scores)

    def _validate_scores(self, raw: dict[str, Any]) -> EvalScores:
        expected_keys = {score.json_key() for score in self._output_scores}
        actual_keys = set(raw.keys())
        if actual_keys != expected_keys:
            raise RuntimeError(
                f"Score key mismatch: got {sorted(actual_keys)}, expected {sorted(expected_keys)}"
            )

        validated: EvalScores = {}
        for key, value in raw.items():
            if isinstance(value, bool):
                raise RuntimeError(
                    f"Score '{key}' returned a bool. Use a float (e.g. 1.0 for pass, 0.0 for fail)."
                )
            if isinstance(value, int):
                try:
                    value = float(value)
                except OverflowError:
                    # int too large for a float, e.g. 10**400
                    raise RuntimeError(
                        f"Score '{key}' must be a finite number, got {value}"
                    ) from None
            if not isinstance(value, float):
                raise RuntimeError(
                    f"Score '{key}' must be a float, got {type(value).__name__}"
                )
            # Fail here, in the scorer's own error surface, rather than at
            # EvalRun save time where the message loses the code-eval context.
            if not math.isfinite(value):
                raise RuntimeError(
                    f"Score '{key}' must be a finite number, got {value}"
                )
            validated[key] = value

        return validated
