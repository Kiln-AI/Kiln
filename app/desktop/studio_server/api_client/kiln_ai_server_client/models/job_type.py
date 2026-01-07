from enum import Enum


class JobType(str, Enum):
    SAMPLE_JOB = "sample-job"

    def __str__(self) -> str:
        return str(self.value)
