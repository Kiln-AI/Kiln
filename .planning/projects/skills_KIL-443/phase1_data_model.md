# Phase 1: Data Model & Validation (COMPLETED)

## Goal

Create the `Skill` Pydantic model with agentskills.io spec validation and disk persistence. All data lives in `skill.kiln` — no separate content directory in V1.

## Files Created/Modified

### `libs/core/kiln_ai/datamodel/skill.py`

```python
from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.utils.validation import ToolNameString


class Skill(KilnParentedModel):
    """A Skill represents reusable agent instructions following the agentskills.io specification.

    Skills are project-level resources that can be attached to run configs.
    """

    name: ToolNameString = Field(
        description="Skill name. Snake_case: lowercase alphanumeric with underscores, 1-64 chars.",
    )
    description: str = Field(
        description="Description of what the skill does and when to use it. 1-1024 chars.",
        min_length=1,
        max_length=1024,
    )
    body: str = Field(
        description="The markdown body content (instructions) of the skill.",
    )

    @classmethod
    def relationship_name(cls) -> str:
        return "skills"

    @classmethod
    def parent_type(cls):
        from kiln_ai.datamodel.project import Project
        return Project
```

### `libs/core/kiln_ai/datamodel/project.py`

Added `"skills": Skill` to the Project's `parent_of` dict and typed `skills()` accessor.

### `libs/core/kiln_ai/datamodel/__init__.py`

Exported the `Skill` class.

### `libs/core/kiln_ai/datamodel/test_skill.py`

23 tests covering validation, persistence, and project integration.

## Key Design Notes

- Fields are `name`, `description`, `body` — matching the standard Kiln model convention (every model uses `name`/`description`).
- The `name` field uses Kiln's `ToolNameString` convention (snake_case, 1-64 chars) for consistency with tool names in the UI. `name` also serves as the directory name via `build_child_dirname`.
- The `body` field stores the markdown instructions. This is the main content the agent reads.
- Fields like `license`, `metadata`, `compatibility` from the agentskills.io spec are omitted — they're only relevant for import/export of external skills (P2). Kiln already tracks authorship via `created_by`.
- No `skill_content/` directory or SKILL.md file on disk. All data lives in `skill.kiln`.
