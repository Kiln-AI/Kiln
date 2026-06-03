---
status: complete
---

# Implementation Plan: Input Transform Create UI

See `functional_spec.md` and `architecture.md` for details. Mostly frontend, plus one stateless endpoint.

## Phases

- [x] **Phase 1 — Foundations: validation endpoint + helpers.**
  Add the `POST /api/validate_input_transform_template` endpoint and its request/response models in `run_config_api.py`, wrapping `compile_template_or_raise` (§Arch 1). Regenerate the OpenAPI client (§Arch 1.1). Add the `buildJinjaInputTransform` and `inputTransformsEqual` helpers to `run_config_formatters.ts` (§Arch 2). Backend endpoint tests + helper unit tests (§Arch 8).

- [ ] **Phase 2 — UI: control, modal, and form wiring.**
  Add `input_transform_create_modal.svelte` (§Arch 3) and `input_transform_selector.svelte` (action-button create/edit, §Arch 4). Render the selector as the last advanced option in `advanced_run_options.svelte`, and wire `input_transform` through `run_config_component.svelte`: state var + the three functions (load-config populate, custom-detection compare, save payload) + reactive dependency list (§Arch 5). Component tests for the modal and selector, plus run-config integration assertions (§Arch 8).
