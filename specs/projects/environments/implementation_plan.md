---
status: complete
---

# Implementation Plan: OpenEnv Environments on the Run Page

Phases follow `architecture.md` section 1. Each phase leaves all checks passing.

## Phases

- [x] Phase 1: Rename World to Environment across core, server, web and tests, with no behaviour change. Delete the `*_worlds*` annotation files and regenerate the OpenAPI schema and annotations (architecture section 2).
- [x] Phase 2: `NamedResetKwargs` and `OpenEnvServer.named_reset_kwargs`, with the create and update routes accepting them (section 3).
- [x] Phase 3: `core/tools/openenv_reach.py`, used on run config save and code tool create; the `run_openenv_server` lookup endpoint; OpenEnv tool sets in `available_tools` with the 5-second timeout (sections 4 and 7, server side).
- [x] Phase 4: Single-turn sessions: `openenv_for_run` in `BaseAdapter.invoke`, `openenv_reset_kwargs` on `AdapterConfig` and `RunTaskRequest`, `openenv_episode` saved on the run, errors mapped to HTTP statuses (section 5).
- [x] Phase 5: Multi-turn sessions: `read_state`, the `ConversationSessions` registry with its reaper, the latest-turn and fork rules, and the delete and shutdown hooks (section 6).
- [x] Phase 6: OpenEnv pages: Tools list rows, the Add Tools item, Connect OpenEnv, the detail page, the Edit OpenEnv and Environment Option dialogs, plus the `code_editor`, `error_details_block` and `settings_item` changes (sections 9 and 10, `ui_design.md`).
- [x] Phase 7: Run page and conversation page: picker rank and `drop_unselectable_tools` exception, the Environment Options field, `openenv_reset_kwargs` in the run request, the OpenEnv property list on runs, the disabled Fork and the session-ended warning, plus the `fancy_select` and `chat_message_actions` changes (sections 7 to 9, `ui_design.md`).
- [ ] Phase 8: Reset argument forms: `OpenEnvSessionManager.reset_schema` reading `/schema` then `/seahaven/schemas`, the `reset_schema` endpoint, the web converter, and the Environment Option dialog's schema form with a Raw JSON toggle, plus any opt-in `run_input_form` change it needs (section 13, `ui_design.md` "Reset Arguments from a schema").
