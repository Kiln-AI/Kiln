from enum import Enum


class BodyStartGepaJobV1JobsGepaJobStartPostTokenBudget(str, Enum):
    HEAVY = "heavy"
    LIGHT = "light"
    MEDIUM = "medium"

    def __str__(self) -> str:
        return str(self.value)
