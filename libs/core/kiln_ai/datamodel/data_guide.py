from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel


class DataGuide(KilnParentedModel):
    """Persistent data guide for synthetic data generation, stored as a child
    of a Task.

    The guide is a single markdown body — typically two top-level sections:
    `# Reference Examples` (user-authored input/output pairs) and
    `# Guidelines & Rules` (structural and semantic constraints, often
    LLM-authored via refine). Either or both may be present; the metaprompter
    treats the whole body as one editable artifact and returns a refined
    version on each refine pass.
    """

    guide: str = Field(
        default="",
        description="Markdown body of the data guide. Typically contains a `# Reference Examples` section and a `# Guidelines & Rules` section.",
    )
