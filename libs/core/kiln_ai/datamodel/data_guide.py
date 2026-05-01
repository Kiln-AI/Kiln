from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel


class DataGuide(KilnParentedModel):
    """Persistent data guide for synthetic data generation, stored as a child
    of a Task. The guide is a markdown string describing structure, rules, and
    examples used to steer synthetic data quality.

    Metadata (id, created_at, created_by, path) is inherited from KilnBaseModel
    via KilnParentedModel so each saved guide carries authorship + timestamps.
    Tasks point at the active guide via `Task.current_data_guide_id`; older
    guides remain on disk so the UI can surface guide history.
    """

    guide: str = Field(
        min_length=1,
        description="The data guide markdown — appended to synthetic data generation prompts to improve sample quality.",
    )
