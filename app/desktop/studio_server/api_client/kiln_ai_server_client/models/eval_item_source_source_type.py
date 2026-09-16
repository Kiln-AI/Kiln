from enum import Enum


class EvalItemSourceSourceType(str, Enum):
    EVAL_INPUT = "eval_input"
    TASK_RUN = "task_run"

    def __str__(self) -> str:
        return str(self.value)
