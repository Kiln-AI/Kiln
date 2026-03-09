# Phase 1: Data Model & Validation

## Goal
Create the `Skill` Pydantic model with agentskills.io spec validation and disk persistence. All data lives in `skill.kiln` — no separate content directory in V1.

## Files to Create/Modify

### New: `libs/core/kiln_ai/datamodel/skill.py`

Create the Skill data model:

```python
from pydantic import Field

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.utils.validation import ToolNameString


class Skill(KilnParentedModel):
    """
    A Skill represents reusable agent instructions following the agentskills.io specification.
    
    Skills are project-level resources that can be attached to run configs.
    """
    
    skill_name: ToolNameString = Field(
        description="Skill name. Snake_case: lowercase alphanumeric with underscores, 1-64 chars.",
    )
    skill_description: str = Field(
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

### Modify: `libs/core/kiln_ai/datamodel/project.py`

Add `Skill` to the Project's `parent_of` dict:

```python
from kiln_ai.datamodel.skill import Skill

class Project(
    KilnParentModel,
    parent_of={
        "tasks": Task,
        "documents": Document,
        "extractor_configs": ExtractorConfig,
        "chunker_configs": ChunkerConfig,
        "embedding_configs": EmbeddingConfig,
        "rag_configs": RagConfig,
        "vector_store_configs": VectorStoreConfig,
        "external_tool_servers": ExternalToolServer,
        "reranker_configs": RerankerConfig,
        "skills": Skill,  # NEW
    },
):
```

This automatically gives Project:
- `project.skills()` method to list all skills
- Proper directory structure: `project_folder/skills/{id} - {name}/skill.kiln`

### Modify: `libs/core/kiln_ai/datamodel/__init__.py`

Export the new `Skill` class.

### New: `libs/core/kiln_ai/datamodel/test_skill.py`

Tests for the Skill model:

1. **Validation tests**:
   - Valid skill names: `"code_review"`, `"a"`, `"my_skill_123"`
   - Invalid skill names: `"Code_Review"` (uppercase), `"_start"` (leading underscore), `"end_"` (trailing), `"double__underscore"`, `""` (empty), `"a" * 65` (too long), `"code-review"` (hyphens)
   - Description length validation (1-1024 chars)

2. **Persistence tests**:
   - Save and load skill from disk
   - Verify skill.kiln file contains correct JSON

3. **Project integration tests**:
   - Create skill as child of project
   - `project.skills()` returns the skill
   - Skill directory created under `project_folder/skills/`

## Key Design Notes

- The `skill_name` field uses Kiln's `ToolNameString` convention (snake_case, 1-64 chars) for consistency with tool names in the UI. Use `skill_name` as the Kiln model `name` for directory naming consistency.
- The `body` field stores the markdown instructions. This is the main content the agent reads.
- Only 3 fields: `skill_name`, `skill_description`, `body`. Fields like `license`, `metadata`, `compatibility` from the agentskills.io spec are omitted — they're only relevant for import/export of external skills (P2). Kiln already tracks authorship via `created_by`.
- No `skill_content/` directory or SKILL.md file on disk. All data lives in `skill.kiln`.
