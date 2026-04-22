# FastAPI / OpenAPI Standards

Our OpenAPI spec drives our SDK, Scalar docs, and agent tool use (Kiln Chat calls our APIs). Every endpoint must be well-documented and consistently named. Flag violations during code review.

**Required on every endpoint:**

1. **`tags=[...]`** on the route decorator. Every endpoint must belong to a tag group (e.g. `tags=["Projects"]`). Untagged endpoints break Scalar navigation and agent tool discovery. Prefer existing tags, creating new ones only when really needed. All tags should be documented in `tags_metadata` in `server.py`
2. **`summary=`** on the route decorator. A short, unique name for the operation. Summaries must be unambiguous — if two endpoints could share the same summary (e.g. "Edit Tags"), qualify them ("Edit Run Tags", "Edit Document Tags").
3. **Docstring** on the handler function (optional if behavior is completely obvious from the path, method, and summary). When provided, docstrings should be terse — one sentence or a fragment. Never pad with filler like "This endpoint allows you to...". Longer descriptions (2–3 sentences) are warranted only when distinguishing easily confused endpoints, documenting non-obvious side effects, or noting prerequisites. Exclude if the `summary` string already covers the same level of detail.
4. **`Path(description=...)`** on every path parameter, using `Annotated[str, Path(description="...")]` syntax. Recurring ID parameters must use consistent standard descriptions (e.g. `"The unique identifier of the project."`, `"The unique identifier of the task within the project."`).
5. **`Query(description=...)`** on every query parameter.
6. **`Field(description=...)`** on Pydantic model properties that aren't completely self-evident from name + type.
7. **Class docstring** on Pydantic models used as API request/response bodies. These become the schema description in the OpenAPI spec, which agents and SDK users see when inspecting request/response types. Optional but suggested if non-obvious from name.

**Correct HTTP methods:**

- **GET** must be idempotent and side-effect-free. If an endpoint creates, modifies, or deletes data, it must not be GET. We previously had GET endpoints that established connections and ran evaluations — this is wrong and confuses both agents and humans.
- **POST** for creation and actions that trigger execution.
- **PATCH** for partial updates.
- **DELETE** for deletion.
- The only exception is SSE streaming endpoints, which must use GET due to browser `EventSource` constraints. These must have descriptions explicitly noting the mutation and the SSE reason.

**Naming and path conventions:**

- **Always use plural nouns** in path segments: `/tasks/{task_id}`, never `/task/{task_id}`. Same for `/projects`, `/specs`, `/evals`, `/runs`, `/prompts`, `/documents`, `/skills`, `/run_configs`, etc. We had inconsistencies where GET used plural but POST/PATCH/DELETE used singular — this is confusing and must be caught.
- **Paths should be descriptive and intuitive.** Paths should follow REST conventions and be clear (as possible) without docstrings. Path and descriptions should distinguishing similar sounding endpoints. If a path could reasonably be improved, suggest a rename.
- **Consistent path structure** for related resources. All operations on the same resource type should share a common path prefix (e.g. all run config operations under `/run_configs`, not split across `/task_run_config`, `/mcp_run_config`, `/run_config`). Important to not use similar but different prefixes, as this commonly trips up agents.
- **No trailing slashes** on paths. Use `/run_configs` not `/run_configs/`. Trailing slashes cause inconsistency between endpoints and can break client routing.

**Example of a well-documented endpoint:**

```python
@app.delete(
    "/api/projects/{project_id}",
    summary="Delete Project",
    tags=["Projects"],
)
async def delete_project(
    project_id: Annotated[
        str, Path(description="The unique identifier of the project.")
    ],
) -> dict:
    """Removes the project from Kiln but does not delete the files from disk."""
```

**What to flag in code review:**

- Missing `tags=` on any route decorator
- Missing `summary=` on any route decorator
- Missing `Path(description=...)` or `Query(description=...)` on any parameter
- GET endpoints that perform mutations (unless SSE with documented justification)
- Singular nouns in path segments where plural is standard
- Ambiguous or duplicate summaries across endpoints
- Trailing slashes on paths
- Inconsistent path naming for the same resource type
- Wordy or filler-padded docstrings ("This endpoint allows you to...")
- Docstrings containing code artifacts, raw `Args:` blocks, or formatting that doesn't read as clean prose in OpenAPI
- SSE endpoints should have `@no_write_lock` annotation (which allows direct streaming). SSE endpoints missing it won't stream.
- Pydantic models used in API request/response types (nested included) missing a class docstring, if the class name alone isn't obvious
- Custom string types with validator-based constraints that don't surface in the OpenAPI schema. Use `StringConstraints` in the `Annotated` type definition so `minLength`/`maxLength` appear automatically (see `FilenameString`, `SkillNameString` for examples). Don't duplicate constraints in individual `Field()` calls.
- **Git sync URL contract.** Any POST/PUT/PATCH/DELETE endpoint that writes to project files (anything under a project's `.kiln` directory) MUST have its path under `/api/projects/{project_id}/...`. `GitSyncMiddleware` only matches that prefix; routes outside it silently bypass git commit/push and will leave the repo dirty. Exceptions are only allowed for endpoints that write to non-project paths (e.g. tmp files, downloads). When reviewing new routes, grep for the route path and confirm it matches the prefix, or confirm the handler writes nothing that belongs in the synced repo.
