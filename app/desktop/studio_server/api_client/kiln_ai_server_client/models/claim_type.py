from enum import Enum


class ClaimType(str, Enum):
    ASSERTION = "assertion"
    EXCLUSION = "exclusion"
    FINAL_JUDGEMENT = "final_judgement"
    INCLUSION = "inclusion"

    def __str__(self) -> str:
        return str(self.value)
