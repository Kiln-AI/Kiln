---
status: draft
---

# Phase 2: UI — control, modal, and form wiring

## Overview

Adds the create/edit modal (`input_transform_create_modal.svelte`), the selector control (`input_transform_selector.svelte`), places it in `advanced_run_options.svelte`, and wires `input_transform` through `run_config_component.svelte` (load, custom-detection, save payload, reactive deps). This is the full authoring UI for input transforms on the /run page.

## Steps

1. Create `input_transform_create_modal.svelte` — a Dialog + FormContainer modal that takes `on_created: (t: InputTransform) => void`, exposes `show(initial_template?)`, holds a monospace textarea, validates via `POST /api/validate_input_transform_template`, and commits on success.

2. Create `input_transform_selector.svelte` — a FancySelect-based control with `export let input_transform: InputTransform | null`, action button for create/edit, and two-value reconcile (none/custom).

3. Update `advanced_run_options.svelte` — add `input_transform` prop, import and render `InputTransformSelector` as the last child.

4. Update `run_config_component.svelte`:
   - Add `input_transform` state var (null).
   - Add it to the reactive dependency list.
   - Thread `bind:input_transform` into both `AdvancedRunOptions` instances.
   - Populate in `update_current_run_options_for_selected_run_config`.
   - Add to custom-detection in `reset_to_custom_options_if_needed`.
   - Include in `run_options_as_run_config_properties` return.

## Tests

- `input_transform_create_modal.test.ts`: empty submit shows error, valid template calls on_created and closes, invalid template shows error and stays open, network error shows error.
- `input_transform_selector.test.ts`: initial null shows None + Create Template; initial set shows Custom Template + Edit Template; pick None clears transform; action button calls modal show; on_created updates transform.
- `run_config_formatters.test.ts`: already has helper tests from Phase 1 (no additions needed).
