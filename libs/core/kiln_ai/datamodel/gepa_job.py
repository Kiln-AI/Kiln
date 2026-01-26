from typing import TYPE_CHECKING

from pydantic import Field

from kiln_ai.datamodel.basemodel import FilenameString, KilnParentedModel

if TYPE_CHECKING:
    from kiln_ai.datamodel.task import Task


class GepaJob(KilnParentedModel):
    """
    The Kiln GEPA job datamodel.
    """

    name: FilenameString = Field(description="The name of the GEPA job.")
    description: str | None = Field(
        default=None,
        description="A description of the GEPA job for you and your team.",
    )
    job_id: str = Field(description="The ID of the job on the remote Kiln server.")
    token_budget: str = Field(
        description="The token budget for this job: 'light', 'medium', or 'heavy'."
    )
    target_run_config_id: str = Field(
        description="The ID of the run configuration used for this job."
    )
    latest_status: str = Field(
        default="pending",
        description="The latest known status of this GEPA job (pending, running, succeeded, failed, cancelled). Not updated in real time.",
    )
    optimized_prompt: str | None = Field(
        default=None,
        description="The optimized prompt result when the job succeeds.",
    )
    created_prompt_id: str | None = Field(
        default=None,
        description="The ID of the prompt created from this job's result, if any.",
    )
    eval_ids: list[str] = Field(
        default_factory=list,
        description="List of eval IDs used for this job.",
    )

    def parent_task(self) -> "Task | None":
        """Get the parent task, with proper typing."""
        if self.parent is None or self.parent.__class__.__name__ != "Task":
            return None
        return self.parent  # type: ignore
