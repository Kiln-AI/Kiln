"""V2 adapter for code_eval: runs user-authored Python scorer in a sandboxed subprocess."""

from threading import Lock
from typing import TYPE_CHECKING, Any

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
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.sandbox_bridge import NestedToolServer, run_bridged_child

_trust_lock = Lock()
_trusted_projects: set[str] = set()


def grant_code_eval_trust(project_path: str) -> None:
    with _trust_lock:
        _trusted_projects.add(project_path)


def revoke_code_eval_trust(project_path: str) -> None:
    with _trust_lock:
        _trusted_projects.discard(project_path)


def is_code_eval_trusted(project_path: str) -> bool:
    with _trust_lock:
        return project_path in _trusted_projects


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

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        props = self.properties
        assert isinstance(props, CodeEvalProperties)

        project_path = self._resolve_project_path()
        if project_path is None or not is_code_eval_trusted(project_path):
            return V2EvalResult(
                skipped_reason=SkippedReason.code_eval_not_trusted,
                skipped_detail="Project not trusted for code eval execution.",
            )

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
                eval_output_schema=BaseEval.build_score_schema(
                    self.eval, allow_float_scores=False
                ),
            ),
            recorder=None,
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
            raise RuntimeError(f"Scorer crashed (exit code {res.exit_code})")

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

        scores = self._validate_scores(raw_scores)
        return V2EvalResult(scores=scores)

    def _resolve_project_path(self) -> str | None:
        try:
            project = self.target_task.parent
            if project is None:
                return None
            return str(project.path) if project.path else None
        except Exception:
            return None

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
                value = float(value)
            if not isinstance(value, float):
                raise RuntimeError(
                    f"Score '{key}' must be a float, got {type(value).__name__}"
                )
            validated[key] = value

        return validated
