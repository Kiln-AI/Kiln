"""V2 adapter for code_eval: runs user-authored Python scorer in a sandboxed subprocess."""

import asyncio
import math
from threading import Lock
from typing import TYPE_CHECKING, Any

from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge

if TYPE_CHECKING:
    from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
    from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.adapters.eval.sandbox_worker import run_scorer
from kiln_ai.datamodel.eval import (
    CodeEvalProperties,
    EvalConfig,
    EvalScores,
    EvalTaskInput,
    SkippedReason,
    V2EvalResult,
)

_trust_lock = Lock()
_trusted_projects: set[str] = set()

_code_eval_execution_lock = asyncio.Lock()


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

        async with _code_eval_execution_lock:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, run_scorer, props.code, inputs, float(props.timeout_seconds)
            )

        if "error" in result:
            tb = result.get("traceback", "")
            msg = result["error"]
            detail = f"{msg}\n{tb}".strip() if tb else msg
            raise RuntimeError(f"Code eval scorer failed: {detail}")

        raw_scores = result.get("ok")
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
            # Fail here, in the scorer's own error surface, rather than at
            # EvalRun save time where the message loses the code-eval context.
            if not math.isfinite(value):
                raise RuntimeError(
                    f"Score '{key}' must be a finite number, got {value}"
                )
            validated[key] = value

        return validated
