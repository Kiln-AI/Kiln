<script lang="ts">
  // Reusable Add/Edit Example dialog used by both the input data guide setup
  // form and the synth page intro. Exposes open_add()/open_edit() methods and
  // dispatches `submit` events with the resulting GuideSample (input only).
  import { createEventDispatcher, onMount } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import TaskRunPicker from "$lib/utils/task_run_picker.svelte"
  import { client } from "$lib/api_client"
  import RunInputFormElement from "$lib/components/run_input_form_element.svelte"
  import {
    model_from_schema_string,
    type SchemaModelProperty,
  } from "$lib/utils/json_schema_editor/json_schema_templates"
  import {
    fetch_task_sample_candidates,
    task_run_to_example,
  } from "$lib/utils/task_sample_example"
  import type { TaskRun } from "$lib/types"
  import type { GuideSample } from "./guide_setup_form.svelte"

  export let project_id: string
  export let task_id: string
  // Existing examples already added to the guide. Used to filter the
  // "Choose from Existing" picker so the user can't double-add the same run.
  export let existing_examples: GuideSample[] = []
  // When true, exposes a third method: "From Documents" — closes this dialog
  // and dispatches `request_documents` so the parent can open its own
  // document-upload dialog. Used by the Kiln Pro setup uploader; the manual
  // setup form leaves this off.
  export let allow_documents: boolean = false

  let example_dialog: Dialog
  let mode: "add" | "edit" = "add"
  let add_method: "manual" | "existing" | null = null
  let editing_index: number = -1
  let editing_input: string = ""
  let editing_task_run_id: string | undefined = undefined

  let available_runs: TaskRun[] = []
  let loading_runs: boolean = true

  // Input JSON schema for structured tasks, fetched on mount. When present, a
  // new manual entry is captured field-by-field (matching the Kiln Pro path)
  // instead of via a free-text textarea.
  let input_json_schema: string | null = null
  let rootFormElement: { buildValue(): unknown } | null = null
  let manual_error: string | null = null
  // Bumped on each open so the structured form re-mounts fresh.
  let formKey = 0

  $: structured_model = (() => {
    if (!input_json_schema) return null
    try {
      return model_from_schema_string(input_json_schema)
    } catch {
      return null
    }
  })() as SchemaModelProperty | null
  // Field-by-field entry only for adding from scratch (the schema form can't be
  // pre-filled, so editing an existing example stays on the textarea).
  $: use_structured_form = mode === "add" && !!structured_model

  $: added_run_ids = new Set(
    existing_examples
      .map((e) => e.task_run_id)
      .filter((id): id is string => !!id),
  )
  $: filtered_available_runs = available_runs.filter(
    (r) => !r.id || !added_run_ids.has(r.id),
  )

  const dispatch = createEventDispatcher<{
    submit: { sample: GuideSample; index: number; mode: "add" | "edit" }
    request_documents: void
  }>()

  function handle_from_documents() {
    example_dialog?.close()
    dispatch("request_documents")
  }

  onMount(async () => {
    try {
      const result = await fetch_task_sample_candidates(project_id, task_id)
      available_runs = result.available_runs.filter(
        (r) => r.input_source?.type !== "synthetic",
      )
    } catch {
      // Non-critical
    } finally {
      loading_runs = false
    }

    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}",
        { params: { path: { project_id, task_id } } },
      )
      input_json_schema = data?.input_json_schema ?? null
    } catch {
      // Non-critical — falls back to the free-text textarea.
    }
  })

  export function open_add() {
    mode = "add"
    add_method = null
    editing_index = -1
    editing_input = ""
    editing_task_run_id = undefined
    manual_error = null
    formKey += 1
    example_dialog?.show()
  }

  export function open_edit(sample: GuideSample, index: number) {
    mode = "edit"
    add_method = "manual"
    editing_index = index
    editing_input = sample.input
    editing_task_run_id = sample.task_run_id
    example_dialog?.show()
  }

  function save_manual() {
    manual_error = null
    let input = editing_input
    if (use_structured_form) {
      if (!rootFormElement) {
        manual_error = "Form not ready."
        return
      }
      try {
        input = JSON.stringify(rootFormElement.buildValue(), null, 2)
      } catch (e) {
        manual_error = e instanceof Error ? e.message : String(e)
        return
      }
    }
    const sample: GuideSample = {
      input,
      task_run_id: mode === "edit" ? editing_task_run_id : undefined,
    }
    dispatch("submit", { sample, index: editing_index, mode })
    example_dialog?.close()
  }

  function select_existing_run(run: TaskRun) {
    const ex = task_run_to_example(run)
    const sample: GuideSample = {
      input: ex.input,
      task_run_id: run.id ?? undefined,
    }
    dispatch("submit", { sample, index: -1, mode: "add" })
    example_dialog?.close()
  }
</script>

<Dialog
  bind:this={example_dialog}
  width="wide"
  title={mode === "edit" ? "Edit Example" : "Add Example"}
  sub_subtitle="Add an example input to guide synthetic input generation."
>
  {#if mode === "add" && add_method === null}
    <!-- Method selection -->
    <div class="flex flex-col gap-4 mt-8">
      {#if filtered_available_runs.length > 0 || allow_documents}
        <button
          class="btn btn-outline mb-2"
          on:click={() => (add_method = "manual")}
          type="button"
        >
          Add Manually
        </button>
      {/if}

      {#if allow_documents}
        <button
          class="btn btn-outline"
          on:click={handle_from_documents}
          type="button"
        >
          From Documents
        </button>
      {/if}

      {#if !loading_runs && filtered_available_runs.length > 0}
        <div class="flex items-center gap-2">
          <div class="flex-1 border-t border-base-300"></div>
          <span class="text-sm text-gray-400">or Select Existing</span>
          <div class="flex-1 border-t border-base-300"></div>
        </div>

        <div class="flex flex-col mt-2 gap-2">
          {#if loading_runs}
            <div class="text-sm text-gray-400">Loading existing samples...</div>
          {:else}
            <TaskRunPicker
              available_runs={filtered_available_runs}
              inputs_only={true}
              on:select={(e) => select_existing_run(e.detail)}
            />
          {/if}
        </div>
      {/if}
    </div>
  {/if}
  {#if (filtered_available_runs.length === 0 && !allow_documents) || add_method === "manual"}
    <!-- Manual input form -->
    <div class="flex flex-col gap-3">
      {#if use_structured_form && structured_model}
        {#key formKey}
          <RunInputFormElement
            property={structured_model}
            level={0}
            path="root"
            hideHeaderAndIndent={true}
            bind:this={rootFormElement}
          />
        {/key}
      {:else}
        <FormElement
          label="Input"
          id="example_input"
          inputType="textarea"
          height="medium"
          bind:value={editing_input}
          optional={true}
          hide_optional_badge={true}
        />
      {/if}
      {#if manual_error}
        <div class="text-error text-sm">{manual_error}</div>
      {/if}
      <div class="flex flex-row gap-2 justify-end mt-2">
        {#if mode === "add" && (filtered_available_runs.length > 0 || allow_documents)}
          <button
            type="button"
            class="btn btn-sm h-10 btn-outline min-w-24"
            on:click={() => (add_method = null)}
          >
            Back
          </button>
        {/if}
        <button
          type="button"
          class="btn btn-sm h-10 btn-primary min-w-24"
          on:click={save_manual}
        >
          {mode === "edit" ? "Save" : "Add"}
        </button>
      </div>
    </div>
  {/if}
</Dialog>
