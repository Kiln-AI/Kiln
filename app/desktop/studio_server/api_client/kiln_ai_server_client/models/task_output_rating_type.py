from enum import Enum


class TaskOutputRatingType(str, Enum):
    CUSTOM = "custom"
    FIVE_STAR = "five_star"
    PASS_FAIL = "pass_fail"
    PASS_FAIL_CRITICAL = "pass_fail_critical"

    def __str__(self) -> str:
        return str(self.value)
