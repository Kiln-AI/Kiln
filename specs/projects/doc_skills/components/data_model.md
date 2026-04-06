---
status: complete
---

# Component: Data Model (`DocumentSkill`)

## File Location

`libs/core/kiln_ai/datamodel/document_skill.py`

## Model Definition

```python
class DocumentSkill(KilnParentedModel):
    name: FilenameString
    is_archived: bool = Field(default=False)
    description: str | None = Field(default=None)
    skill_name: SkillNameString
    skill_content_header: str = Field(min_length=1, max_length=16384)
    extractor_config_id: ID_TYPE
    chunker_config_id: ID_TYPE
    document_tags: list[str] | None = Field(default=None)
    skill_id: ID_TYPE | None = Field(default=None)
    strip_file_extensions: bool = Field(default=True)
```

## Validation

Add a `@model_validator(mode="after")` following the same pattern as `RagConfig.validate_tags`:

```python
@model_validator(mode="after")
def validate_document_skill(self):
    if self.document_tags is not None:
        if len(self.document_tags) == 0:
            raise ValueError("Document tags cannot be an empty list.")
        for tag in self.document_tags:
            if not tag:
                raise ValueError("Document tags cannot be empty.")
            if " " in tag:
                raise ValueError("Document tags cannot contain spaces. Try underscores.")

    if self.skill_name.strip() == "":
        raise ValueError("Skill name cannot be empty.")
    if self.skill_content_header.strip() == "":
        raise ValueError("Skill content header cannot be empty.")

    return self
```

## Project Registration

In `libs/core/kiln_ai/datamodel/project.py`:

1. Add import: `from kiln_ai.datamodel.document_skill import DocumentSkill`
2. Add to `parent_of` dict: `"document_skills": DocumentSkill`
3. Add typed accessor method:

```python
def document_skills(self, readonly: bool = False) -> list["DocumentSkill"]:
    return DocumentSkill.all_children_of_parent_path(self.path, readonly=readonly)
```

The `parent_of` registration gives `DocumentSkill`:
- A `parent_type()` returning `Project`
- A `relationship_name()` returning `"document_skills"`
- Disk storage at `{project_path}/document_skills/{id}/document_skill.kiln`

## Helper Method

Add a `parent_project()` convenience method (same pattern as `RagConfig` and `Skill`):

```python
def parent_project(self) -> Union["Project", None]:
    if self.parent is None or self.parent.__class__.__name__ != "Project":
        return None
    return self.parent  # type: ignore
```

## Tests

File: `libs/core/kiln_ai/datamodel/test_document_skill.py`

Test cases:
- Valid creation with all fields
- Valid creation with minimal fields (optional fields omitted)
- Tag validation: empty list, empty string in list, spaces in tags
- `skill_name` validation: empty, invalid chars (SkillNameString handles this)
- `skill_content_header` validation: empty, whitespace-only
- Save/load round-trip via `save_to_file()` / `from_id_and_parent_path()`
- `parent_project()` returns correct parent
- `skill_id` starts as `None`, can be set
- `strip_file_extensions` defaults to `True`
- Listing via `project.document_skills()` returns correct set
