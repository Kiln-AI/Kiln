from enum import Enum


class JobType(str, Enum):
    GEPA_JOB = "gepa-job"
    SAMPLE_JOB = "sample-job"

    def __str__(self) -> str:
        return str(self.value)
