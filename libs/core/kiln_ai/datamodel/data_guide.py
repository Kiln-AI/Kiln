from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel


class DataGuide(KilnParentedModel):
    """Persistent data guide for synthetic data generation, stored as a child
    of a Task. Split into two fields to make the user-owned vs LLM-owned
    boundary explicit at the data layer:

    - `examples_md`: user-authored reference examples — the body of the
      `# Reference Examples` section (the sequence of `## Example N` blocks
      with fenced ```input / ```output code fences). Never written by the
      LLM. The `# Reference Examples` heading itself is added by the
      composer at runtime, not stored here.
    - `rules_md`: LLM-authored rules — the body of the `# Guidelines & Rules`
      section (XML-tagged group blocks containing `## <title>` rule blocks).
      Refresh-replaced wholesale by the metaprompter on each refinement.
      The `# Guidelines & Rules` heading itself is added by the composer.

    Either may be empty; a guide with neither is not useful but the model
    permits it (validation lives at the save endpoint).
    """

    examples_md: str = Field(
        default="",
        description="Body of the `# Reference Examples` section — user-authored reference examples (sequence of `## Example N` blocks with fenced input/output). The heading itself is not stored here; it is added by the runtime composer.",
    )
    rules_md: str = Field(
        default="",
        description="Body of the `# Guidelines & Rules` section — LLM-authored rules (XML-tagged group blocks). The heading itself is not stored here; it is added by the runtime composer.",
    )
