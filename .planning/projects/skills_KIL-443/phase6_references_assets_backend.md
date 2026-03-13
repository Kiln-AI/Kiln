# Phase 6: References & Assets — Backend

## Goal

Add backend support for `references/` and `assets/` directories alongside `SKILL.md`. Enable agents to load reference files on demand via the skill tool's `resource` parameter. Provide file management API endpoints.

## Disk Layout

```
skills/<id> - <name>/
  skill.kiln
  SKILL.md
  references/          # Markdown docs the agent can load on demand
    REFERENCE.md
    finance.md
    ...
  assets/              # Static resources (images, data files, templates)
    schema.json
    diagram.png
    ...
```

## Files to Create / Modify

### Modify: `libs/core/kiln_ai/datamodel/skill.py`

Add methods for managing references and assets:

```python
def references_dir(self) -> Path:
    return self.path.parent / "references"

def assets_dir(self) -> Path:
    return self.path.parent / "assets"

def list_references(self) -> list[str]:
    """List filenames in the references/ directory."""
    ref_dir = self.references_dir()
    if not ref_dir.exists():
        return []
    return sorted(f.name for f in ref_dir.iterdir() if f.is_file())

def read_reference(self, filename: str) -> str:
    """Read a reference file's content. Raises ValueError if not found or path traversal."""
    ...  # Validate filename (no path traversal), read file, return content

def save_reference(self, filename: str, content: str) -> None:
    """Write a reference file. Creates references/ dir if needed."""
    ...  # Validate filename, create dir, write file

def delete_reference(self, filename: str) -> None:
    """Delete a reference file."""
    ...

def list_assets(self) -> list[dict]:
    """List assets with metadata (filename, size, type)."""
    ...

def asset_path(self, filename: str) -> Path:
    """Get the full path to an asset file. Validates against path traversal."""
    ...

def save_asset(self, filename: str, content: bytes) -> None:
    """Write an asset file. Creates assets/ dir if needed."""
    ...

def delete_asset(self, filename: str) -> None:
    """Delete an asset file."""
    ...
```

**Security**: All filename methods must validate against path traversal (no `..`, no absolute paths, no slashes). Reject filenames that would escape the skill directory.

### Modify: `libs/core/kiln_ai/tools/skill_tool.py`

Add a `resource` parameter to the tool schema and `run()` method:

```python
async def toolcall_definition(self) -> ToolCallDefinition:
    return {
        "type": "function",
        "function": {
            "name": await self.name(),
            "description": await self.description(),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the skill to load.",
                    },
                    "resource": {
                        "type": "string",
                        "description": "Optional. Path to a specific resource file within the skill (e.g. 'references/REFERENCE.md'). If omitted, returns the skill's main instructions.",
                    },
                },
                "required": ["name"],
            },
        },
    }

async def run(self, context=None, **kwargs) -> ToolCallResult:
    skill_name = kwargs.get("name")
    resource = kwargs.get("resource")
    ...
    skill = self._skills.get(skill_name)
    ...

    if resource:
        # Load a specific resource file
        return self._load_resource(skill, resource)
    else:
        # Load the main skill body
        return ToolCallResult(output=skill.body())

def _load_resource(self, skill: Skill, resource: str) -> ToolCallResult:
    """Load a resource file from references/ or assets/ directory."""
    # Only allow references/ and assets/ prefixes
    # Validate path (no traversal)
    # Read and return content
    ...
```

**Update skill description**: The tool description (or system prompt) should mention available resources when a skill has references, so the agent knows it can load them. Consider listing reference filenames in the skill's XML listing.

### Modify: `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`

Update the skills system prompt (around line 302) to explain the two-step reference loading pattern. The current prompt says "load it before proceeding" but doesn't mention the `resource` parameter. Add:

```python
"When handling a request:\n\n"
"1. Determine whether a Skill is relevant.\n"
"2. If a relevant Skill exists, load it by calling skill(name=\"skill_name\").\n"
"3. Follow the instructions and workflow defined in the Skill.\n"
"4. If the Skill's instructions reference additional files (e.g. references/), "
"load them on demand by calling skill(name=\"skill_name\", resource=\"references/filename.md\"). "
"Only load references when the instructions indicate they are needed for the current task.\n\n"
```

This teaches the agent the progressive disclosure pattern: load the skill body first, then conditionally load references based on what the instructions say.

### New: `app/desktop/studio_server/skill_file_api.py`

API endpoints for managing reference and asset files:

```python
def connect_skill_file_api(app: FastAPI):

    @app.get("/api/projects/{project_id}/skills/{skill_id}/references")
    async def list_references(project_id: str, skill_id: str) -> list[str]:
        skill = _get_skill(project_id, skill_id)
        return skill.list_references()

    @app.get("/api/projects/{project_id}/skills/{skill_id}/references/{filename}")
    async def get_reference(project_id: str, skill_id: str, filename: str) -> dict:
        skill = _get_skill(project_id, skill_id)
        content = skill.read_reference(filename)
        return {"filename": filename, "content": content}

    @app.put("/api/projects/{project_id}/skills/{skill_id}/references/{filename}")
    async def save_reference(project_id: str, skill_id: str, filename: str, body: ReferenceContent) -> dict:
        skill = _get_skill(project_id, skill_id)
        skill.save_reference(filename, body.content)
        return {"filename": filename}

    @app.delete("/api/projects/{project_id}/skills/{skill_id}/references/{filename}")
    async def delete_reference(project_id: str, skill_id: str, filename: str) -> None:
        skill = _get_skill(project_id, skill_id)
        skill.delete_reference(filename)

    @app.get("/api/projects/{project_id}/skills/{skill_id}/assets")
    async def list_assets(project_id: str, skill_id: str) -> list[dict]:
        skill = _get_skill(project_id, skill_id)
        return skill.list_assets()

    @app.post("/api/projects/{project_id}/skills/{skill_id}/assets")
    async def upload_asset(project_id: str, skill_id: str, file: UploadFile) -> dict:
        skill = _get_skill(project_id, skill_id)
        content = await file.read()
        skill.save_asset(file.filename, content)
        return {"filename": file.filename}

    @app.delete("/api/projects/{project_id}/skills/{skill_id}/assets/{filename}")
    async def delete_asset(project_id: str, skill_id: str, filename: str) -> None:
        skill = _get_skill(project_id, skill_id)
        skill.delete_asset(filename)
```

### Modify: `app/desktop/studio_server/server.py`

Register the new file API: `connect_skill_file_api(app)`

## Testing

1. **Skill model**: `list_references()`, `read_reference()`, `save_reference()`, `delete_reference()` — happy path + edge cases (empty dir, missing file, path traversal attempts)
2. **Skill model**: `list_assets()`, `save_asset()`, `delete_asset()`, `asset_path()` — same
3. **Path traversal security**: Verify filenames like `../../../etc/passwd`, `foo/../bar`, absolute paths are all rejected
4. **SkillTool resource param**: `run(name="x", resource="references/REFERENCE.md")` returns file content, invalid resource returns error, path traversal blocked
5. **System prompt**: Verify updated prompt includes reference loading instructions
6. **API endpoints**: CRUD for references and assets, file upload, 404 for missing files, 400 for invalid filenames
7. **Integration**: Create skill with references and assets, verify agent can load them via tool

## Key Design Notes

- References are **text files** (primarily markdown) — content is sent as strings via JSON API
- Assets are **binary files** — uploaded via `multipart/form-data` (FastAPI `UploadFile`)
- Path traversal is the main security concern — validate all filenames strictly
- The SkillTool `resource` parameter only allows `references/` and `assets/` prefixes
- Reference filenames should follow a convention (lowercase, no spaces, `.md` extension encouraged) but this isn't strictly enforced beyond path safety
- Consider a file size limit for assets (e.g. 10MB) to prevent abuse
