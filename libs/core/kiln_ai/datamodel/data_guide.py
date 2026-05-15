from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel


class DataGuide(KilnParentedModel):
    """Persistent input data guide for synthetic data generation, stored as a
    child of a Task.

    The guide describes what realistic *inputs* to this task look like — input
    shape, format, distribution, and the kinds of values inputs contain. It is
    consumed at the topic and input generation stages of synthetic data
    generation, never at the output stage. Output behavior is the job of the
    task's system prompt, not this guide.

    The guide is a single markdown body with up to two top-level sections:
    `# Reference Inputs` (user-authored example inputs) and `# Input
    Guidelines & Rules` (structural and semantic constraints on inputs, often
    LLM-authored via refine). Either or both may be present; the metaprompter
    treats the whole body as one editable artifact and returns a refined
    version on each refine pass.
    """

    guide: str = Field(
        default="",
        description="Markdown body of the input data guide. Typically contains a `# Reference Inputs` section and a `# Input Guidelines & Rules` section.",
    )
