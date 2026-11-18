from enum import Enum


class JobType(str, Enum):
    DATA_GUIDE_JOB = "data-guide-job"
    SAMPLE_JOB = "sample-job"

    def __str__(self) -> str:
        return str(self.value)
