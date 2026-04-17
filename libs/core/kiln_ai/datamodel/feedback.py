from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.datamodel.datamodel_enums import FeedbackSource


class Feedback(KilnParentedModel):
    """Feedback on a task run.

    Supports multi-source feedback: different users, automated systems, and
    different locations in the UI can each contribute independent feedback
    entries on the same task run.
    """

    feedback: str = Field(
        min_length=1,
        description="Free-form text feedback on the task run.",
    )
    source: FeedbackSource = Field(
        description="Where this feedback originated, e.g. 'run-page' or 'spec-feedback'.",
    )
