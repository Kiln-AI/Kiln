# Phase 5: SKILL.md Storage Refactor

## Goal

Move `body` out of the `skill.kiln` JSON file and into a `SKILL.md` sidecar file (YAML frontmatter + markdown body), following the agentskills.io spec. `name` and `description` stay as Pydantic fields in `skill.kiln` for fast listing/search. They are also written to the SKILL.md frontmatter (kept in sync on save) so the file conforms to the agentskills.io format. `body` becomes a method that reads from SKILL.md — only accessed when the agent loads a skill.

## Disk Layout (After)

```
skills/<id> - <name>/
  skill.kiln    →  { "id": "...", "name": "my_skill", "description": "Does X...", "created_by": "...", "is_archived": false }
  SKILL.md      →  ---
                    name: my_skill
                    description: Does X when Y happens. Use for Z.
                    ---
                    ## Instructions
                    The markdown body content here...
```

**What lives where:**
- `skill.kiln`: `id`, `name`, `description`, `is_archived`, `created_by`, `created_at` — everything needed for fast listing/dropdown display
- `SKILL.md`: `name` (frontmatter), `description` (frontmatter), body (markdown content) — full agentskills.io format
- `name` and `description` are duplicated across both files (kept in sync). `body` is only in SKILL.md.

## Files to Modify

### Modify: `libs/core/kiln_ai/datamodel/skill.py`

Remove `body` as a Pydantic field. Keep `name` and `description` as fields (loaded from `skill.kiln`). Add `body()` method that reads from `SKILL.md`, and `save_skill_md()` that writes the full SKILL.md file using the model's current `name`/`description` values.

```python
class Skill(KilnParentedModel):
    name: ToolNameString = Field(...)
    description: str = Field(min_length=1, max_length=1024, ...)
    is_archived: bool = Field(default=False, ...)

    # body is NOT a Pydantic field — stored in SKILL.md only

    SKILL_MD_FILENAME = "SKILL.md"

    def skill_md_path(self) -> Path:
        """Path to the SKILL.md file (sibling of skill.kiln)."""
        if self.path is None:
            raise ValueError("Skill path not set")
        return self.path.parent / self.SKILL_MD_FILENAME

    def body(self) -> str:
        """Read markdown body from SKILL.md (content after frontmatter)."""
        ...  # Parse file, skip frontmatter, return body content

    def save_skill_md(self, body: str) -> None:
        """Write SKILL.md with YAML frontmatter (from self.name/self.description) + markdown body.

        Validates body (non-empty) before writing. Uses self.name and self.description
        for the frontmatter, keeping them in sync with skill.kiln.
        """
        if not body or not body.strip():
            raise ValueError("body must be non-empty")
        frontmatter = f"---\nname: {self.name}\ndescription: {self.description}\n---\n"
        content = frontmatter + body
        self.skill_md_path().write_text(content, encoding="utf-8")
```

**Key simplification**: `save_skill_md()` takes only `body` as an argument. It reads `self.name` and `self.description` from the Pydantic model to write the frontmatter, so the SKILL.md is always in sync with `skill.kiln`. No way for them to drift.

**body validation**: `body` is validated in `save_skill_md()` (non-empty). Pydantic still validates `description` (1-1024 chars) since it remains a field.

**YAML frontmatter parsing**: Use `yaml` (PyYAML, already a dependency) to parse frontmatter when reading. The format is standard YAML between `---` delimiters. Only the body content after the closing `---` is returned by `body()`.

**No caching needed**: `description` is loaded from `skill.kiln` (fast, already cached by `ModelCache`). Only `body()` reads from SKILL.md, and that only happens when an agent loads a skill — not during listing.

### Modify: `libs/core/kiln_ai/tools/skill_tool.py`

Only `body` access changes:

```python
# Line 73: skill.body → skill.body()
return ToolCallResult(output=skill.body())
```

`s.name` and `s.description` remain field access (no change needed). The `_skills` dict is built from `s.name` (still a field).

### Modify: `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`

No change needed. `s.name` and `s.description` are still Pydantic fields:

```python
# Line 302: unchanged — s.description is still a field
skill_lines = "\n".join(f"- {s.name}\n  {s.description}" for s in skills)
```

### Modify: `app/desktop/studio_server/skill_api.py`

**Create endpoint**: Accept `description` and `body` in the request, create the Skill with name + description (saves `skill.kiln`), then call `save_skill_md(body)`:

```python
async def create_skill(project_id: str, skill_data: SkillCreationRequest) -> dict:
    project = project_from_id(project_id)
    skill = Skill(name=skill_data.name, description=skill_data.description, parent=project)
    skill.save_to_file()
    skill.save_skill_md(skill_data.body)
    return skill_to_response(skill)
```

**GET endpoints**: Return type changes from `Skill` to a dict/response model that includes `body()`:

```python
def skill_to_response(skill: Skill) -> dict:
    result = skill.model_dump()
    result["body"] = skill.body()
    return result
```

`description` is already in `model_dump()` since it's a Pydantic field. Only `body` needs to be added explicitly.

**Update endpoint**: `SkillUpdateRequest` needs to support updating `description` and `body`. When `description` changes, update the field + `save_to_file()` + `save_skill_md()` (to keep SKILL.md in sync). When `body` changes, call `save_skill_md()`:

```python
class SkillUpdateRequest(BaseModel):
    is_archived: bool | None = None
    description: str | None = None
    body: str | None = None
```

On update:
1. Apply `is_archived` and/or `description` to the model if present
2. `save_to_file()` to write `skill.kiln`
3. If `description` or `body` changed, call `save_skill_md(body)` — it reads `self.name`/`self.description` from the model, so SKILL.md stays in sync

**`SkillCreationRequest`**: Unchanged (already has `name`, `description`, `body` fields with validation).

### Modify: `app/desktop/studio_server/tool_api.py`

No change needed. `skill.description` is still a Pydantic field:

```python
# Lines 326-329: unchanged
ToolApiDescription(
    id=build_skill_tool_id(skill.id),
    name=skill.name,
    description=skill.description,
)
```

### Modify: `libs/core/kiln_ai/datamodel/test_skill.py`

Update tests:
- Creating a Skill no longer takes `body` as a constructor arg — save via `save_skill_md(body)` after `save_to_file()`
- `skill.description` remains field access (unchanged)
- Assertions change from `skill.body` to `skill.body()`
- Add tests for SKILL.md parsing (valid frontmatter, missing frontmatter, malformed YAML)
- Add tests for `save_skill_md()` validation (empty body)
- Add test for round-trip: save then read back
- Add test that `skill.kiln` does NOT contain `body`
- Add test that SKILL.md frontmatter `name`/`description` match `skill.kiln` values

### Modify: `app/desktop/studio_server/test_skill_api.py`

Update test fixtures:
- `sample_skill_data` fixture unchanged (API still accepts `name`, `description`, `body`)
- `saved_skill` fixture needs to call `save_skill_md(body)` after `save_to_file()`
- Response assertions unchanged (API still returns `description` and `body` in the response)

### Modify: `libs/core/kiln_ai/tools/test_skill_tool.py`

Update skill fixtures to use `save_skill_md(body)`. Assertions on `skill.body` become `skill.body()`.

### Modify: `libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py`

Update any test fixtures that create Skills — remove `body` from constructor, add `save_skill_md()` call.

## Call Site Summary

Only `body` access changes. `name` and `description` remain Pydantic field access (unchanged).

| File | Line | Change |
|------|------|--------|
| `skill_tool.py` | 73 | `skill.body` → `skill.body()` |
| `base_adapter.py` | 302 | No change (`s.description` still a field) |
| `tool_api.py` | 328 | No change (`skill.description` still a field) |
| `skill_api.py` | create | Remove `body` from Skill constructor, add `save_skill_md(body)` call |
| `skill_api.py` | GET | Add `body()` to response dict |
| `skill_api.py` | update | Handle `body` updates via `save_skill_md()` |

## Testing

1. **SKILL.md parsing**: Valid frontmatter, missing file, malformed YAML, empty body
2. **save_skill_md validation**: Empty body rejected
3. **Round-trip**: Create skill → save_skill_md → read body() → match
4. **skill.kiln doesn't contain body**: Save a skill, read the JSON, verify no `body` key
5. **skill.kiln contains description**: Save a skill, verify `description` is in JSON
6. **Sync**: Save skill, verify SKILL.md frontmatter `name`/`description` match skill.kiln values
7. **API integration**: Create via API, GET returns description and body correctly
8. **Update sync**: Update description via API, verify both skill.kiln and SKILL.md frontmatter are updated
9. **Backward compat**: Consider a migration path for existing skills that have `body` in skill.kiln (read from JSON if SKILL.md doesn't exist, then migrate)

## Key Design Notes

- `name` and `description` stay as Pydantic fields in `skill.kiln` for fast listing/dropdown display
- `name` and `description` are also written to SKILL.md frontmatter (for agentskills.io spec compliance) — kept in sync because `save_skill_md()` reads from `self.name`/`self.description`
- `body` lives only in SKILL.md — read on demand via `body()` method, only when the agent loads the skill
- `save_to_file()` writes `skill.kiln` only. `save_skill_md(body)` writes SKILL.md. The API layer calls both.
- The two write paths (create and update in `skill_api.py`) are the only places that write skill data — sync is straightforward
- YAML frontmatter parsing is straightforward — standard `---` delimiters with PyYAML
