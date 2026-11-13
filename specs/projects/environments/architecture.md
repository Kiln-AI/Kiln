---
status: complete
---

# Architecture: OpenEnv Environments on the Run Page

This doc covers how to build `functional_spec.md` and `ui_design.md`. It's one doc rather than component designs: each part is small, and the hard parts are how the parts connect.

File paths are relative to the repo root. `core` means `libs/core/kiln_ai`, `server` means `libs/server/kiln_server`, `studio` means `app/desktop/studio_server` and `web` means `app/web_ui/src`.

## 1. Phases

| Phase | What | Why this order |
|---|---|---|
| 1 | Rename World to Environment | Everything after it uses the new names. A pure rename is easiest to review on its own. |
| 2 | `named_reset_kwargs` and the Environment API | Data the later phases read |
| 3 | Reach check, save-time validation, lookup endpoint | Shared by the run path and the UI |
| 4 | Single-turn sessions: run API, library | The core feature |
| 5 | Multi-turn session registry | Builds on phase 4 |
| 6 | OpenEnv pages (Tools area) | UI on phase 2's API |
| 7 | Picker, run page, conversation page, run sidebar | UI on phases 3 to 5 |
| 8 | Reset argument forms from the server's reset schema | Added after phase 7; only the Environment Preset dialog reads it (section 13) |

Phases 6 and 7 include the small shared-component changes they need (section 9).

## 2. Phase 1: the rename

World is on `origin/main` (commit `6a1820f37`) but in no release, so there's no migration code. Three open branches (`leonard/code-tool-world-tools`, `leonard/eval-job-worlds`, `sfierro/synthetic-worlds-eb`) will resolve conflicts themselves. Existing dev projects are converted by an offline script outside the repo.

### Name map

| Today | Renamed |
|---|---|
| `core/datamodel/world.py`, `World` | `core/datamodel/openenv.py`, `OpenEnvServer` |
| `Project.worlds()`, `parent_of={"worlds": World}` | `Project.openenv_servers()`, `{"openenv_servers": OpenEnv}` |
| On disk: `worlds/<id> - <name>/world.kiln` | `openenv_servers/<id> - <name>/openenv_server.kiln` (follows from the class and `parent_of` names) |
| `WorldReset`, `.world_id` | `OpenEnvReset`, `.openenv_server_id` |
| `WorldEpisode`, `.world_version` | `OpenEnvEpisode`, `.openenv_version` |
| `EvalInput.world_reset` | `EvalInput.openenv_reset` |
| `TaskRun.world_episode`, `EvalTaskInput.world_episode` | `TaskRun.openenv_episode`, `EvalTaskInput.openenv_episode` |
| `to_sandbox_dict()` keys `world_id`, `world_version` | `openenv_server_id`, `openenv_version` |
| Code scorer kwarg `world_episode` (`sandbox_worker.py`), judge variable `{{ world_episode... }}` | `openenv_episode` |
| `WORLD_TOOL_ID_PREFIX = "kiln_tool::world::"`, `build_world_tool_id`, `world_and_tool_name_from_id` | `OPENENV_TOOL_ID_PREFIX = "kiln_tool::openenv::"`, `build_openenv_tool_id`, `openenv_and_tool_name_from_id` |
| `core/tools/world_tool.py` | `core/tools/openenv_tool.py` (`OpenEnvToolProxy` keeps its name) |
| `core/worlds/` package | `core/openenv/` |
| `WorldSessionManager` protocol, `world_version()` | `OpenEnvSessionManager`, `openenv_version()` |
| `_ServerInfo.world_id`, `.world_version`, `_compose_world_version` | `.openenv_server_id`, `.openenv_version`, `_compose_openenv_version` |
| `EpisodeContext.world`, `.session_manager: WorldSessionManager` | `.openenv`, `OpenEnvSessionManager` |
| `validate_world_tool_ids` (`adapter_registry.py`) | `validate_openenv_tool_ids` (rewritten in phase 3) |
| `world_trace_tag` (`trace_index.py`) | `openenv_trace_tag` |
| Eval runner: `_WorldTarget`, `_world_*` helpers, `world_session_manager` kwarg, `_WorldToolMismatch` literals `"no_world_reset"`, `"other_world"` | `_OpenEnvTarget`, `_openenv_*`, `openenv_session_manager`, `"no_openenv_reset"`, `"other_openenv"` |
| `studio/world_api.py`, `/api/projects/{project_id}/worlds...`, `World*Request/Response`, tag "Worlds" | `studio/openenv_server_api.py`, `/openenv_servers...`, `OpenEnv*Request/Response`, tag "Environments" |

`OpenEnvSessionManager`, `OpenEnvToolProxy` and `OpenEnvTool` keep their names.

### Order and gotchas

1. Datamodel, then the `openenv/` package, then tools, adapters and eval, then the studio APIs and `server.py`'s OpenAPI tag. Tests last, renaming `test_world.py`, `test_world_api.py`, `test_world_tool.py` and `test_eval_runner_worlds.py`.
2. Replace `world_id` and `world_version` before bare `world`, so they become `openenv_server_id` and `openenv_version`.
3. Don't touch English or geometry uses of "world": hello-world strings, `lib/utils/lineage/*`, `lineage_canvas.svelte`, `synth_data_guidance_datamodel.ts`, `batch_plan_guidance.ts` and `synthetic_user`'s "world-state".
4. Rewrite prose by hand where a blind replace doubles up, such as "the world's environment".
5. Don't rename existing `env` names: `url`, `_ServerInfo`, `ENV_NAME`, local MCP `env_vars`, and SvelteKit's `$app/environment`.
6. Fix the hard-coded `kiln_tool::world::{world.id}` string in `eval_runner.py` (around line 454) to use the constant.
7. Delete the `libs/server/kiln_server/utils/agent_checks/annotations/*_worlds*.json` files. Regenerate annotations with `dump_annotations.py`, and regenerate `web/lib/api_schema.d.ts` with `generate_schema.sh`.
8. Finish with a repo-wide grep for `kiln_tool::world`, `world_`, `World` and `worlds`. Every remaining hit must be English.

Existing trace-index digests change, because the reset's field names change. Eval traces are regenerated once. That's acceptable before release.

## 3. Phase 2: data model and Environment API

### Data model (`core/datamodel/openenv.py`)

```python
class NamedResetKwargs(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    reset_kwargs: dict[str, JsonValue] = Field(default_factory=dict)

class OpenEnvServer(KilnParentedModel):
    ...existing fields...
    named_reset_kwargs: list[NamedResetKwargs] = Field(default_factory=list)
    is_archived: bool = False

    @field_validator("named_reset_kwargs")
    @classmethod
    def unique_names(cls, v): ...  # ValueError "An Environment Preset named {name} already exists."
```

- Names are compared after `strip()`, case-sensitively.
- `KilnBaseModel` has `validate_assignment=True`, so the validator also runs on PATCH.
- List order is insertion order. The first entry is the default.
- `reset_kwargs` is typed as a dict, so a JSON array or scalar is rejected by Pydantic. The API maps that to the spec's message (below).
- `description` and `is_archived` are additive with defaults, so files saved without them load.

### API (`studio/openenv_server_api.py`)

- `OpenEnvServerCreateRequest`, `OpenEnvServerUpdateRequest` and `OpenEnvServerResponse` gain `named_reset_kwargs` (each entry with its optional `description`), and `_openenv_server_response` copies it. The response also carries `is_archived`.
- **Reachable on save, mirroring MCP's `validate_tool_server_connectivity`:** create calls `OpenEnvSessionManager.check_reachable(openenv_server)` before `save_to_file()` when `url` is set; update calls it only when the new `url` differs from the saved one. `check_reachable` does the same `GET {url}/metadata` as `openenv_version`, but caches nothing, so an unsaved record can be checked. An `OpenEnvError` becomes a 400 with its message, and nothing is saved. Update applies its changes to a deep copy, so a refused update leaves no trace on a cached record.
- **Archive, mirroring `POST /tool_servers/{id}/archive`:** `POST /api/projects/{project_id}/openenv_servers/{openenv_server_id}/archive` with `{"is_archived": bool}` sets the flag and returns the server. It doesn't contact the server. Agent policy: requires approval, like the other writes on this router.
- PATCH replaces the whole list. The UI sends the full list after an add, edit, clone or remove. One environment file is the unit of write, so there are no per-entry routes.
- Validation errors return 400 with the friendly text from `ui_design.md`'s Copy table. These are a duplicate name, "Reset arguments must be a JSON object.", and the URL error "Enter a full URL starting with http:// or https://...". The URL message replaces the developer text raised by `validate_url`, which stays as the internal message.
- The UI never calls DELETE. The route and its 409 rule stay.
- `GET /openenv_servers/{openenv_server_id}/tools` is unchanged.

## 4. Phase 3: reach check, validation, lookup endpoint

### The reach walk (`core/tools/openenv_reach.py`, new)

```python
@dataclass(frozen=True)
class OpenEnvReach:
    openenv_server_id: str
    via: str            # "directly", "code tool <name>", "Kiln task tool <name>"

def openenv_reach(project: Project, tool_ids: list[ToolId]) -> list[OpenEnvReach]: ...
def single_openenv_server_id(project: Project, tool_ids: list[ToolId]) -> str | None:
    """None if no environment is reached. Raises OpenEnvReachError naming each
    environment and how it's reached if there's more than one."""
```

- It walks breadth-first with a `visited` set of tool ids, so cycles end.
- A direct `kiln_tool::openenv::` id yields its environment id.
- A code tool id is loaded with `CodeTool.from_id_and_parent_path(code_tool_id_from_tool_id(tid), project.path)`, and the walk recurses into its `tool_allowlist`. The `via` text is the outermost code tool's name.
- A Kiln task tool id is resolved to its server via `kiln_task_server_id_from_tool_id`. The walk then follows `properties["task_id"]` and `["run_config_id"]` to the target run config's `tools_config.tools` and recurses. This is the same lookup as `KilnTaskTool._run_config`.
- Missing code tools, servers or run configs are skipped. Other validation reports those.
- It reads only ids, never code, and makes no network calls.

`OpenEnvReachError(ValueError)` carries the spec's message: "Your tools use more than one OpenEnv server (Acme, Beta). A run can only use one." The detail text adds the `via` for each environment, for logs and the save error.

### Where it runs

| Caller | Change |
|---|---|
| `validate_openenv_tool_ids` (`adapter_registry.py`), used by `validate_run_config_tool_names` when a run config is saved | Replace the direct-only check with `single_openenv_server_id` over all tools. Keep the existence and name-collision checks. |
| Code tool create (`studio/code_tool_api.py`, around line 234, via `validate_unique_allowlist_tool_names`) | Call `single_openenv_server_id(project, allowlist)` |
| Run start (section 5) | Called by the session setup |
| Lookup endpoint (below) | Called directly |

### Lookup endpoint (`studio/openenv_server_api.py`)

```
POST /api/projects/{project_id}/tasks/{task_id}/run_openenv_server
body:     {"tool_ids": [ToolId, ...]}
response: {"openenv_server": OpenEnvServerResponse | null, "error": str | null}
```

- It returns 200 in every normal case. `error` is set when more than one environment is reached. `openenv` is null when none is.
- If the reached environment no longer exists, it returns `error`: "OpenEnv [id] wasn't found."
- It makes no network calls, so it's fast enough to call on every tool change. The UI debounces calls by 250 ms.

## 5. Phase 4: single-turn sessions

### Where the session lives

All environment setup goes in core, in a new module `core/openenv/run_session.py`. It's called from `BaseAdapter.invoke`, so the run API, the Python library and Kiln task tool sub-runs all behave the same.

```python
class OpenEnvRunError(Exception):
    kind: Literal["reach", "not_found", "unreachable", "at_capacity",
                  "reset_rejected", "session_ended", "fork_refused",
                  "not_started_with_openenv", "kwargs_without_openenv"]
    message: str   # user-facing, from the Copy table

@asynccontextmanager
async def openenv_for_run(task, run_config_properties, reset_kwargs, parent_run,
                              session_manager=None) -> AsyncIterator[OpenEnvRunHandle | None]:
    ...
```

- `AdapterConfig` gains `openenv_reset_kwargs: dict[str, JsonValue] | None = None`, and `RunTaskRequest` gains the same field. The run API copies it into `AdapterConfig`.
- `BaseAdapter.invoke` wraps the existing body in `openenv_for_run(...)`. This happens before the try block that wraps errors in `KilnRunError`, so setup errors stay `OpenEnvRunError`.

### Sub-runs

- A Kiln task tool sub-run, or any adapter invoked while `get_episode()` is set, uses the current episode.
- It doesn't open a new one.
- It records `openenv_episode` only on the top-level run.

### What `openenv_for_run` does

1. If an episode is already active (`get_episode()` is not None), yield `None`. This is the sub-run case above.
2. `openenv_server_id = single_openenv_server_id(project, tools)`. On `OpenEnvReachError`, raise `kind="reach"`.
3. If there's no `openenv_server_id`: when `reset_kwargs` is set, raise `kwargs_without_openenv`. Otherwise yield `None`, and the run is unchanged.
4. Load the environment. If it's missing, raise `not_found`.
5. Single-turn task:
   - Call `start_episode(env, reset_kwargs or {})`, and build `EpisodeContext` with tools from `list_tools(env)`, as the eval runner's `_load_openenv_target` does.
   - Transient errors and `capacity_reached` become `at_capacity`. Connection errors become `unreachable`, and `OpenEnvRejectedError` on reset becomes `reset_rejected`, each with the server's message.
   - `set_episode(...)` and yield the handle.
   - On normal exit, `end_episode` and set `handle.episode`. On an exception, `release` and re-raise.
   - Always `reset_episode(token)`.
6. Multi-turn task: see section 6.

After the context exits, `invoke` sets `run.openenv_episode = handle.episode`. It saves the run again if it was saved, which is the case when `allow_saving` is set and the run has a path. The run is saved twice; the eval runner already does the same.

### Errors to HTTP (`server/run_api.py`)

`run_task` catches `OpenEnvRunError` and raises `HTTPException`:

| kind | Status |
|---|---|
| `reach`, `kwargs_without_openenv`, `reset_rejected` | 400 |
| `not_found` | 404 |
| `session_ended`, `fork_refused`, `not_started_with_openenv` | 409 |
| `unreachable` | 502 |
| `at_capacity` | 503 |

- The run page and multi-turn composer already show `{"message": ...}` errors in the form error line, as the spec wants.
- Errors after the model starts (a run-ending tool error) still become `KilnRunError`, shown as "Run Failed", unchanged.
- The capacity hint (`_CAPACITY_HINT`) is eval-specific today. Pass a context-specific hint: the spec's at-capacity copy for runs, and the existing text for evals.

## 6. Phase 5: multi-turn sessions

### New session-manager method

`OpenEnvSessionManager.read_state(episode) -> dict[str, JsonValue]` sends OpenEnv `state()` and leaves the session open. Implement it in `OpenEnvSessionManager`, under the per-session lock, and in `core/openenv/testing.py`'s fake. On failure it raises like `call_tool` does, and drops the session.

### Registry (`core/openenv/conversations.py`, new)

```python
@dataclass
class HeldSession:
    episode: OpenEnvEpisode
    context: EpisodeContext
    turn_run_ids: set[str]     # every turn in this conversation, for the fork check
    last_used: float           # time.monotonic()

class ConversationSessions:
    def take(self, parent_run_id: str) -> HeldSession | None
    def put(self, latest_run_id: str, held: HeldSession) -> None
    def holds_turn(self, run_id: str) -> bool          # any held session includes this turn
    async def release_runs(self, run_ids: Iterable[str]) -> None
    async def reap(self, idle_seconds: float = 1800) -> None
    async def close_all(self) -> None

def shared_conversation_sessions() -> ConversationSessions
```

- One process-wide instance, keyed by the latest turn's run id, guarded by one `asyncio.Lock`.
- A reaper task starts lazily on the first `put`. It runs `reap()` every 60 seconds and calls `release` for sessions idle longer than 30 minutes. It's built like `BackgroundSync` (`app/desktop/git_sync/background_sync.py`), using `create_task` and stopping by cancellation.
- `shutdown_shared_session_manager()` calls `close_all()` first, and the desktop lifespan already calls it at shutdown.

### Multi-turn flow in `openenv_for_run`

| Request | Behaviour |
|---|---|
| First turn (no parent) | Start the episode as in single-turn and set it. After the turn, `read_state` gives the turn's `openenv_episode.final_state`. `put(new_run_id, held)`. |
| Later turn, `take(parent_id)` finds a session | Set its context and ignore `reset_kwargs`, because the choice is locked. After the turn, `read_state`, record it, and `put(new_run_id, held)` with `turn_run_ids` updated. |
| Later turn, no session, `holds_turn(parent_id)` is true | Raise `fork_refused`: "This conversation uses an OpenEnv server, so it can only continue from the latest turn." |
| Later turn, no session, parent has `openenv_episode` | Raise `session_ended`, with the spec's message |
| Later turn, parent has no `openenv_episode`, tools now reach an environment | Raise `not_started_with_openenv`: "This conversation started without an OpenEnv server. Start a new conversation to use one." |
| The turn raises | If `is_run_ending_tool_error`, release the session. Otherwise `put(parent_id, held)` back, so the user can retry the same turn. |

`take` removes the entry, so two concurrent sends on the same turn can't share a session. The second one gets `session_ended`. The UI already blocks double sends.

### Delete hook

`DELETE .../runs/{run_id}` and bulk delete in `server/run_api.py` call `shared_conversation_sessions().release_runs(deleted_ids)` after a successful delete. That releases any held session whose key, the latest turn, was deleted.

## 7. Phase 3 and 7: `available_tools` and the picker

### Server (`studio/tool_api.py`)

- Add `ToolSetType.OPENENV = "openenv"`.
- After the MCP loop, list every environment that has a `url` and isn't archived concurrently: `asyncio.gather` over `asyncio.wait_for(shared_session_manager().list_tools(env), timeout=5)`.
- An environment that fails or times out is skipped, the same as MCP, and logged at warning level.
- Each listed environment gives a set with `set_name="OpenEnv Server: " + env.name`, like `"MCP Server: " + server.name`. Its tools are `ToolApiDescription(id=build_openenv_tool_id(env.id, t.name), name=t.name, description=t.description, function_name=t.name)`.

### Web

- `web/lib/ui/run_config_component/tool_options.ts`: add `openenv` to `AGENT_TOOL_SET_RANK`, ranked after `mcp` and before `demo`. The record is exhaustive, so TypeScript requires it.
- `tools_selector.svelte`, `drop_unselectable_tools`: keep ids starting with `kiln_tool::openenv::` whose server isn't archived (`keeps_unlisted_openenv_tool` in `lib/utils/openenv.ts`). Without this, an offline environment's tools would be removed from a saved selection.
- An archived server's tools are dropped, as an archived MCP server's are. Once a selected tool is an OpenEnv one, the picker reads `GET /openenv_servers` once per project (`load_archived_openenv_server_ids`) to learn which servers are archived. Until it answers, or if it fails, nothing is dropped.

### What archive does, mirroring MCP

| Where | Archived MCP server | Archived OpenEnv server |
|---|---|---|
| `available_tools` | Left out | Left out |
| Tool picker | Its tools aren't offered; a selection holding them drops them | The same |
| Saved run configs | Still list the tools, and still run: `tool_from_id` doesn't check the flag | The same: the reach walk and `OpenEnvTool` don't check it |
| Tools list | "Archived" status | "Archived" status, listed last |
| Detail page | Archive / Unarchive, and a warning | The same |

## 8. Phase 7: run page, conversation page, run sidebar

### Environment Preset field

- New file: `web/lib/ui/run_config_component/environment_preset_field.svelte`. It's rendered by `run_config_component.svelte` at the bottom of the Advanced Options collapse, after `AdvancedRunOptions`. The collapse starts closed but keeps its content mounted, so `get_openenv_reset_kwargs()` works while it's closed. It sits there because it appears only after the lookup answers, and outside the collapse that shifted the page.
- It watches `get_tools()` and debounces calls to the lookup endpoint by 250 ms. Its states:

| State | Shown |
|---|---|
| `openenv` null, no error | Nothing (hidden) |
| `error` set | The label, plus the error line in FormElement's error style |
| Environment with no presets | Empty state, "No Environment Presets" with "Add Environment Preset" linking to the detail page |
| Environment with presets | A `fancy_select` of presets in order, first selected, each option's description the preset's own description (none when it has none) |

- The run page reads the selection through `run_config_component.get_openenv_reset_kwargs()`, which returns the chosen preset's `reset_kwargs` or null. A failed lookup is retried once and then thrown, and the more-than-one-server error is refused again by the run API, so the field being collapsed can't let a bad run through. It includes them as `openenv_reset_kwargs` in the `/run` body.
- The multi-turn composer sends it only on the first turn.
- It's not stored in the run config or in `localStorage`.

### Conversation page and run sidebar

- `run_sidebar.svelte` and the conversation page's sidebar read `run.openenv_episode`. They show a `PropertyList` titled "OpenEnv" after Usage, with OpenEnv Server (a link to the detail page), Version (`openenv_episode.openenv_version`) and Reset Arguments (formatted JSON).
- The conversation page adds a prop to `lib/ui/trace/chat_message_actions.svelte`: `fork_disabled_reason: string | null`. When the conversation has `openenv_episode`, Fork is disabled on earlier turns, with that text as a tooltip.
- A `session_ended` 409 from the composer shows above the composer as an error `Warning`, using the existing error display.

## 9. Shared component changes

| Component | Change |
|---|---|
| `lib/components/code_editor.svelte` | Add `language: "python" \| "json" = "python"`. Import `@codemirror/lang-json` dynamically when it's `"json"`. Add the package to `web/package.json`. |
| `lib/ui/error_details_block.svelte` | Add `full_width = false`. When it's true, drop `max-w-[600px] mx-auto`. |
| `lib/ui/settings_item.svelte` (via `kiln_section.svelte` items) | Add optional `link_label` and `link_href`, rendered on its own line under the description as an `<a class="link">`. |
| `lib/components/run_input_form_element.svelte` | An optional enum's dropdown starts on "Not Set", listed first (`enum_select_options` in `run_input_select_options.ts`). A required enum keeps "Select an option" with "Not Set" last. This changes every optional enum in the run input form, which is intended. |
| `lib/ui/trace/chat_message_actions.svelte` | Add `fork_disabled_reason` (section 8) |

Each change is opt-in, so existing callers render exactly as before.

## 10. OpenEnv pages (phase 6)

These are routes under `web/routes/(app)/tools/[project_id]/`, as listed in `ui_design.md`'s page inventory: `add_tools/openenv/+page.svelte`, `openenv_servers/[openenv_server_id]/+page.svelte`, and the Tools list and Add Tools changes.

- The Environment Preset dialog (`environment_preset_dialog.svelte`) edits a local copy of `named_reset_kwargs` and PATCHes the whole list. It has Name, an optional Description, and a Reset Arguments section headed by `SettingsHeader` with the Raw JSON / Form link in its actions slot.
- The presets table shows Name, Description and Reset Arguments, one truncated line each, and expands a row on click (the synthetic data tables' pattern). `compact_reset_arguments` gives the one-line JSON.
- Archive and Unarchive call the archive route, then reload `available_tools`.
- Clone opens the Add dialog prefilled, with the name `"<name> (copy)"`.
- Remove PATCHes the list without that entry.
- New type aliases go in `web/lib/types.ts`.

## 11. Testing

Python uses pytest, following `python_test_guide.md`. Web uses vitest, following the existing component test patterns.

| Area | Tests |
|---|---|
| Rename | The full existing suite passes after the rename. A grep test fails on any `kiln_tool::world` or `World` identifier left in non-English source. |
| `NamedResetKwargs` | Unique names, including after PATCH. A non-object JSON is rejected. Order is preserved. Round-trip on disk. |
| Environment API | Create and patch with `named_reset_kwargs`, including descriptions. The friendly error messages. Create and URL-changing update refuse an unreachable server and save nothing; other updates don't contact it. Archive and unarchive. |
| `openenv_reach` | Direct ids. Nested code tools. A Kiln task tool into a run config into a code tool. Cycles terminate. Missing targets are skipped. One environment versus two, and the error text names each `via`. |
| Save validation | Run config save refuses two environments reached indirectly. Code tool create refuses an allowlist that reaches two. |
| Lookup endpoint | The three result shapes, plus a missing environment |
| `openenv_for_run` (fake session manager from `openenv/testing.py`) | No environment: a no-op. Kwargs without an environment. Single-turn start, set, end, and `openenv_episode` saved twice. Release on exception. Each error kind, and its HTTP mapping in run API tests. A sub-run reuses the episode. |
| `read_state` | Returns state, keeps the session open, drops it on failure |
| `ConversationSessions` | Put and take re-keying. Fork refused. Session ended. Not started with an environment. Retry after a non-ending error. Reap after idle, with an injected clock. `release_runs`. `close_all`. |
| Run API multi-turn | Three turns share one episode. Each turn's `openenv_episode.final_state` comes from `read_state`. The run delete hook releases the session. |
| `available_tools` | An OpenEnv set is listed. An offline or archived environment is skipped. The timeout is respected. |
| Web | `tool_options` rank, `drop_unselectable_tools` keeping env ids and dropping archived ones, all four `environment_preset_field` states and its place in Advanced Options, optional enums leading with "Not Set", the component prop defaults (each new prop off renders as before), and the request body including `openenv_reset_kwargs` |
| Reset schema (phase 8) | Core: `/schema` with `reset`, fallback to `/seahaven/schemas`, neither, a non-object `reset`, unreachable. Endpoint: no url, 502, null and a schema. Web: the converter on the Seahaven schema shape (nullable `anyOf`, `$ref` to `$defs`, enums, defaults) and each unsupported construct returning null; `kwargs_fit_form` true and false cases; empty fields left out; the dialog's three states (no schema, form, Raw JSON locked on) and the toggle round trip. |

After each phase, run `uv run ./checks.sh --agent-mode`, and regenerate the API schema when an endpoint changes.

## 12. Decisions made here

These follow from the spec and the code. They're listed so a reviewer can disagree before implementation.

- **Session setup lives in core, in `BaseAdapter.invoke`,** not in the run API. Without that, the library and Kiln task tool sub-runs would need their own path.
- **Multi-turn sessions are keyed by the latest turn's run id.** There's no conversation id in Kiln, and this key makes "only the latest turn" automatic.
- **Later turns ignore `openenv_reset_kwargs`.** The choice is locked at the first turn.
- **After a non-ending error, the session goes back under the parent turn,** so retrying the same message works.
- **`available_tools` checks each environment with a 5-second timeout, in parallel,** so one slow server doesn't stall the picker.
- **The eval runner keeps its own session code.** Only its names change. Merging it with `openenv_for_run` is a later cleanup.

## 13. Phase 8: reset argument forms

Behaviour is in the functional spec (Reset argument forms) and `ui_design.md` (Reset Arguments from a schema).

### Reading the schema (`core/openenv/session_manager.py`)

`OpenEnvSessionManager.reset_schema(openenv_server) -> dict[str, JsonValue] | None`:

- Uses `httpx.AsyncClient` with `CONNECT_TIMEOUT_S`, as `_connect_remote` does for `/metadata`. It is always fresh: nothing is cached.
- `GET {url}/schema`. If the answer is a JSON object whose `reset` is a JSON object, return that.
- Otherwise `GET {url}/seahaven/schemas` and do the same. A 404 there means no schema.
- Return `None` when neither has one. Raise `OpenEnvError` with the existing "can't reach" wording when the server can't be reached, as `list_tools` does.
- The Seahaven fallback is one clearly commented block, so it can be deleted once Seahaven serves `reset` on `/schema`.

### Endpoint (`studio/openenv_server_api.py`)

`GET /api/projects/{project_id}/openenv_servers/{openenv_server_id}/reset_schema` returns `OpenEnvServerResetSchemaResponse { reset_schema: dict | None }`. It returns 400 when the record has no url, with the same message as the tools route, and 502 on `OpenEnvError` or `ValueError`. Tag "OpenEnv Servers", `ALLOW_AGENT`. Add its agent-check annotation and regenerate the API schema.

### Converter (`web/lib/utils/openenv_reset_schema.ts`, new)

Kiln's schema form reads `JsonSchemaProperty` (`lib/utils/json_schema_editor/json_schema_templates.ts`), which has no `anyOf`, `$ref` or `default`. Pydantic's `model_json_schema()` uses all three. The converter is a pure function:

- `reset_schema_to_form_schema(schema: unknown): JsonSchemaProperty | null`
  - Resolves local `$ref`s (`#/$defs/...`). A missing or cyclic ref returns null.
  - Collapses `anyOf: [X, {type: "null"}]` to X, and marks that property not required.
  - Keeps `title`, `description`, `enum`, `type`, `properties` and `required`. Drops `default` and `additionalProperties: false`.
  - Returns null for the whole schema when it meets anything else: another `anyOf`, `oneOf` or `allOf`, a `type` list, a property with no type, or an object with no `properties` (a free-form dict). The dialog then stays on the JSON editor.
- `kwargs_fit_form(kwargs, form_schema): { fits: true } | { fits: false, reason: string }`. Every key must be a known property, and every value must match its property's type or enum, recursively. `null` doesn't fit, because the form can't produce it.
- `form_value_to_kwargs(value)`: drops empty strings, `undefined` and `null`, and objects left empty after that, recursively.

### Dialog (`routes/(app)/tools/[project_id]/openenv_servers/[openenv_server_id]/environment_preset_dialog.svelte`)

- On open, call `load_openenv_server_reset_schema` (new, in `lib/api/openenv_server_api.ts`). Any error, or a null schema, means no schema. The error isn't shown: the detail page already shows offline state.
- With a form schema, render `run_input_form.svelte` with `input_schema` set to the converted schema as a string, and `hide_label`. Read the value with `get_structured_input_data()`, then pass it through `form_value_to_kwargs`.
- Prefill for Edit and Clone, and the switch from Raw JSON back to the form, need a way to set the form's structured value. If `run_input_form` has none, add an opt-in method such as `set_structured_input_data(value)`, as a shared-component change in its own commit, the same way the phase 6 and 7 components were changed. Existing callers must render exactly as before.
- The Raw JSON toggle uses the control that `frontend_controls.md` names for an inline on/off switch. Its state lives only in the dialog.

### Not in this phase

The run records are unchanged. They still show the saved `reset_kwargs` as JSON.
