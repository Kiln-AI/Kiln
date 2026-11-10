---
status: complete
---

# Functional Spec: OpenEnv Environments on the Run Page

## Summary

Today a run config can list OpenEnv tools, but only the eval runner can run them, and they have no UI. This project lets people connect OpenEnv environments in the app and run a task against one on the run page.

An environment gets a list of named reset kwargs, such as "Acme Manager" and "Acme Tech". When the selected run config can reach an environment's tools, the run page shows an "Environment Options" dropdown of those names. The run starts a session on the environment, reset with the chosen kwargs.

An environment is any OpenEnv server. Kiln doesn't care how it's built. Most are copies of a product, often built with Kiln Seahaven, but one could call real systems. UI copy says "copy of your product", never "synthetic" or "mock".

Swapping a run config between synthetic and real tools (staging, prod) is V2. See the end of this spec.

## Naming

Today's code calls these "worlds". This project renames them to environments, in code and files as well as the UI. Nothing has shipped in a release yet, so this is the cheapest time to do it.

| Today | Renamed |
|---|---|
| `World` (`datamodel/world.py`) | `OpenEnvServer` (`datamodel/openenv.py`) |
| `worlds/<id> - <name>/world.kiln` | `openenv_servers/<id> - <name>/openenv_server.kiln` |
| `Project.worlds()` | `Project.openenv_servers()` |
| `kiln_tool::world::<id>::<tool>` | `kiln_tool::openenv::<id>::<tool>` |
| `/api/projects/{project_id}/worlds` | `/api/projects/{project_id}/openenv_servers` |
| `WorldReset`, `EvalInput.world_reset` | `OpenEnvReset`, `EvalInput.openenv_reset` |
| `WorldEpisode`, `TaskRun.world_episode` | `OpenEnvEpisode`, `TaskRun.openenv_episode` |
| `kiln_ai/worlds/session_manager.py` | `kiln_ai/openenv/session_manager.py` |
| `WorldReset.world_id`, `WorldEpisode.world_version` | `OpenEnvReset.openenv_server_id`, `OpenEnvEpisode.openenv_version` |
| `world_api.py`, `validate_world_tool_ids` | `openenv_server_api.py`, `validate_openenv_tool_ids` |

`OpenEnvSessionManager` keeps its name, since it already names the protocol.

The UI uses "OpenEnv" for the thing, the way MCP servers are shown as "MCP Server" while the data model is `ExternalToolServer`. Named reset kwargs are called "Environment Options" in the UI, and the kwargs themselves "Reset Arguments". UI copy never says "kwargs", "world", "synthetic" or "mock".

The rename is its own first phase: a pure rename with no behaviour change, so it's easy to review. Dev projects, the `eb3` scripts and any code judge reading `world_episode` are converted by hand, outside the Kiln repo.

## Scope

In scope:

- The rename above.
- `named_reset_kwargs` on `OpenEnvServer`.
- OpenEnv pages in the Tools area, next to MCP servers: Add Tools, Connect OpenEnv, the detail page and Edit OpenEnv.
- Adding `@codemirror/lang-json` so the code editor can edit JSON.
- OpenEnv tools in the tool picker.
- The "Environment Options" dropdown on the run page.
- Environment sessions for run page runs and the run API, single-turn and multi-turn.
- One environment per run, checked across everything a run can reach.
- A Kiln Seahaven callout on the Connect OpenEnv page.

Out of scope:

- `ToolDefinition`s and swapping real tools for synthetic ones. These are V2.
- Changes to evals beyond the rename. Eval inputs keep their own `openenv_reset`.
- Eval Builder generating data tied to an environment. This is a separate spec.
- A free-form JSON override for reset kwargs on the run page.
- Running environment tools from the code tool test panel. A call there fails with a clear error.
- A default Environment Option other than the first one added (P2).
- Deleting an environment from the UI.
- Saving a snapshot of an environment's tools, or Kiln starting an environment's server. Like a remote MCP server, an environment must be running for its tools to be picked or run.
- Migration code. Environments haven't shipped in any release.

## Named reset kwargs

`OpenEnvServer` gains:

```python
class NamedResetKwargs(BaseModel):
    name: str                    # e.g. "Acme Tech"
    reset_kwargs: dict[str, Any] # e.g. {"fixture": "acme", "role": "tech"}

class OpenEnvServer:
    named_reset_kwargs: list[NamedResetKwargs] = []
```

Rules:

- Names are required and unique within an environment.
- `reset_kwargs` is opaque to Kiln and passed to the environment's `reset` as-is. It can be empty.
- The dropdown shows entries in the order they were added. Kiln has no user-ordered lists, so entries can't be reordered.
- Entries can be added, edited, cloned and removed. Clone prefills a new entry named "[name] (copy)". Removing needs no confirmation. Past runs aren't affected, because each run saves the kwargs it used.
- The UI calls each entry an "Environment Option".

## OpenEnv pages

Environments are managed in the Tools area, next to MCP servers. See `ui_design.md`.

- **Connect and edit:** name, description and `url`. The existing create and update routes are reused. The URL stays editable, because a local server's port can change, and a new environment would mean a new id in every saved tool id. Each run records the version the server reported.
- **Tools:** the detail page shows the tools the environment serves, read live from `GET /api/projects/{project_id}/openenv_servers/{openenv_server_id}/tools`. If it's offline, the page shows the error instead.
- **Environment Options:** each entry is a name and a JSON editor for its kwargs, using the app's code editor in JSON mode. Invalid JSON, or JSON that isn't an object, is shown inline and blocks saving.
- **No delete in V1:** the UI has no way to delete an environment. The existing delete route and its rule (refused while a saved eval input resets into the environment) are unchanged.
- **Seahaven:** a callout at the top of the Connect OpenEnv page promotes Kiln Seahaven (https://github.com/Kiln-AI/Seahaven) for people who don't have an environment yet.
- **Docs:** the OpenEnv item on Add Tools ends with a "Learn more" link to the OpenEnv docs page, which needs writing.

## Tool picker

Environment tools appear in the tool picker, grouped as "OpenEnv: Acme", like "MCP Server: Docs Search".

- Each tool shows the name the environment serves. These names can't be renamed in Kiln.
- Environment tools come from `available_tools`, which already lists each MCP server's tools live.
- An offline environment is hidden from the picker, like an MCP server that can't be reached. Tools already selected from it stay selected (the picker never drops `kiln_tool::openenv::` ids), so Run fails with the can't-reach error rather than the selection silently changing. Showing an offline group is a possible later change.
- Nothing is disabled. Tools from several environments can be selected, and the one-environment error appears in the Environment Options field and when Run is clicked.

## One environment per run

A run can reach at most one environment. The environment ids a run can reach are collected from:

- The run config's tools.
- The allowlists of code tools it lists, including code tools nested inside those code tools.
- The run configs of Kiln task tools it lists. A Kiln task tool's sub-run shares the parent's session.

Every environment tool id names its environment (`kiln_tool::openenv::<openenv_server_id>::<tool>`), so this is a check on lists of ids, never on code. A code tool can only call tools on its allowlist.

The check runs:

- On the run page, as tools are selected. The Environment Options field shows the error in place of the dropdown.
- When a run config is saved. Today's check only covers the run config's own tools.
- When a run starts, before any model call.
- In code tool allowlist editing, where a code tool's allowlist can't reach more than one environment itself.

## Run page

### The Environment Options dropdown

- It appears only when the selected run config, saved or unsaved, can reach an environment's tools.
- It's labelled "Environment Options" and lists the environment's named reset kwargs by name, in order.
- The first entry is selected by default.
- If the environment has no Environment Options, the dropdown shows "No Environment Options" and a link to its page. The run resets with no kwargs. If the environment needs some, its error is shown.
- Changing the run config to one that reaches no environment hides the dropdown.
- If the selected tools reach more than one environment, the field shows the error in place of the dropdown: "Your tools use more than one OpenEnv (Acme, Beta). A run can only use one." Clicking Run returns the same error.

### Environment sessions

A run with an environment starts a session before the model is called, resetting with the chosen kwargs. The session is held by Kiln's server, not the browser.

Single-turn tasks:

- The session starts with the run and closes when the run ends. The final state is saved on the run.

Multi-turn tasks:

- The Environment Options choice is locked when the conversation starts.
- One session lasts for the whole conversation, across turns.
- The session closes after 30 minutes without a turn, when the app exits, or when the conversation is deleted. Leaving the page doesn't close it, because browsers don't reliably report that and the conversation page can be reopened.
- Each turn's run saves the environment's state at the end of that turn.
- If the session is gone for any reason, sending a message shows an error: "The OpenEnv session for this conversation ended. Start a new conversation to keep using this OpenEnv." The history stays readable. Kiln never silently starts a new session, because the agent would be in a different state from the one in its history.
- Continuing from anything but the latest turn is refused in a conversation with an environment, because its state has moved past it.

### Run records

Each run with an environment saves `openenv_episode` as evals do today, including the reset kwargs it used and the final state. A saved run shows the environment and those kwargs, not the option's name, because options can be renamed or removed later.

## Run API and library

The page runs through the run API, so these changes apply to every caller:

- **Run API:** the run request takes optional `openenv_reset_kwargs`. The environment comes from the run config. Sending kwargs for a config that reaches no environment is refused.
- **Python library:** the adapter's config takes the same option.
- **Kiln Assistant:** gets the same option through the run API.

The API takes kwargs, not a name, so callers outside the app aren't tied to an environment's named list.

## Errors

Every error says what failed and how to fix it. Each of these happens before the model is called:

- The run reaches more than one environment. The error names them and where each is reached.
- The environment can't be found, is offline or is at capacity. OpenEnv servers need `max_concurrent_envs` high enough for open chats as well as eval jobs.
- The environment rejects the reset kwargs. Its error is shown.

A session lost during or between turns fails that run with the error above.

## Existing text this changes

- `kiln_ai/run_context.py` says world tool ids can never resolve in API, chat or export code paths. They now resolve in run page and run API runs that have a session.
- `kiln_ai/adapters/adapter_registry.py` says only the eval runner starts an episode.

## Constraints

- No client names in specs, code, tests or commits.
- Nothing changes for projects with no environments, or for run configs that reach none.
- Evals behave as they do today, apart from the rename.

## V2: swapping real and synthetic tools

Planned next, not built in this project. The goal is to run the same run config against synthetic environments, staging and prod. The object that does the swap needs a new name, since "Environment" now means an OpenEnv server.

- A **`ToolDefinition`** saves what the model sees: `tool_function_name`, `tool_description`, `parameters_schema`. It's immutable. Run configs and code tools list definitions instead of environment or MCP tool ids.
- A **mapping object (name TBD)** maps definitions to real tools (OpenEnv or MCP), with an environment id and default reset kwargs. It's append-only and archived rather than deleted.
- Eval inputs replace `openenv_reset` with a setup that names the mapping object and optional reset kwargs.
- A mapped tool must accept everything its definition can send. This is checked on save and at run start.
- Code judges have no mapping.

V1's Environment Options may become the source of V2's default reset kwargs.
