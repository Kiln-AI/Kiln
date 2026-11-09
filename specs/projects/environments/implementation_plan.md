---
status: complete
---

# Implementation Plan: OpenEnv Environments on the Run Page

Phases follow `architecture.md` section 1. Each phase leaves all checks passing.

## Phases

- [x] Phase 1: Rename World to Environment across core, server, web and tests, with no behaviour change. Delete the `*_worlds*` annotation files and regenerate the OpenAPI schema and annotations (architecture section 2).
- [x] Phase 2: `NamedResetKwargs` and `Environment.named_reset_kwargs`, with the create and update routes accepting them (section 3).
- [ ] Phase 3: `core/tools/env_reach.py`, used on run config save and code tool create; the `run_environment` lookup endpoint; OpenEnv tool sets in `available_tools` with the 5-second timeout (sections 4 and 7, server side).
- [ ] Phase 4: Single-turn sessions: `environment_for_run` in `BaseAdapter.invoke`, `env_reset_kwargs` on `AdapterConfig` and `RunTaskRequest`, `env_episode` saved on the run, errors mapped to HTTP statuses (section 5).
- [ ] Phase 5: Multi-turn sessions: `read_state`, the `ConversationSessions` registry with its reaper, the latest-turn and fork rules, and the delete and shutdown hooks (section 6).
- [ ] Phase 6: OpenEnv pages: Tools list rows, the Add Tools item, Connect OpenEnv, the detail page, the Edit OpenEnv and Environment Option dialogs, plus the `code_editor`, `error_details_block` and `settings_item` changes (sections 9 and 10, `ui_design.md`).
- [ ] Phase 7: Run page and conversation page: picker rank and `drop_unselectable_tools` exception, the Environment Options field, `env_reset_kwargs` in the run request, the OpenEnv property list on runs, the disabled Fork and the session-ended warning, plus the `fancy_select` and `chat_message_actions` changes (sections 7 to 9, `ui_design.md`).
