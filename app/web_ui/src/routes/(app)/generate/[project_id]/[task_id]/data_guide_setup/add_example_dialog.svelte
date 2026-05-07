<script lang="ts">
  // Reusable Add/Edit Example dialog used by both the data guide setup form
  // and the synth page intro. Exposes open_add()/open_edit() methods and
  // dispatches `submit` events with the resulting GuideSample.
  import { createEventDispatcher, onMount } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import TaskRunPicker from "$lib/utils/task_run_picker.svelte"
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

  let example_dialog: Dialog
  let mode: "add" | "edit" = "add"
  let add_method: "manual" | "existing" | null = null
  let editing_index: number = -1
  let editing_input: string = ""
  let editing_output: string = ""
  let editing_task_run_id: string | undefined = undefined

  let available_runs: TaskRun[] = []
  let loading_runs: boolean = true

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
  }>()

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
  })

  export function open_add() {
    mode = "add"
    add_method = null
    editing_index = -1
    editing_input = ""
    editing_output = ""
    editing_task_run_id = undefined
    example_dialog?.show()
  }

  export function open_edit(sample: GuideSample, index: number) {
    mode = "edit"
    add_method = "manual"
    editing_index = index
    editing_input = sample.input
    editing_output = sample.output
    editing_task_run_id = sample.task_run_id
    example_dialog?.show()
  }

  function save_manual() {
    const sample: GuideSample = {
      input: editing_input,
      output: editing_output,
      task_run_id: mode === "edit" ? editing_task_run_id : undefined,
    }
    dispatch("submit", { sample, index: editing_index, mode })
    example_dialog?.close()
  }

  function select_existing_run(run: TaskRun) {
    const ex = task_run_to_example(run)
    const sample: GuideSample = {
      input: ex.input,
      output: ex.output,
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
  sub_subtitle="Add a task data example to guide generation."
>
  {#if mode === "add" && add_method === null}
    <!-- Method selection -->
    <div class="flex flex-col gap-4 mt-8">
      {#if filtered_available_runs.length > 0}
        <button
          class="btn btn-outline mb-2"
          on:click={() => (add_method = "manual")}
          type="button"
        >
          Add Manually
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
              on:select={(e) => select_existing_run(e.detail)}
            />
          {/if}
        </div>
      {/if}
    </div>
  {/if}
  {#if filtered_available_runs.length === 0 || add_method === "manual"}
    <!-- Manual input/output form -->
    <div class="flex flex-col gap-3">
      <FormElement
        label="Input"
        id="example_input"
        inputType="textarea"
        height="medium"
        bind:value={editing_input}
        optional={true}
        hide_optional_badge={true}
      />
      <FormElement
        label="Output"
        id="example_output"
        inputType="textarea"
        height="medium"
        bind:value={editing_output}
        optional={true}
        hide_optional_badge={true}
      />
      <div class="flex flex-row gap-2 justify-end mt-2">
        {#if mode === "add" && filtered_available_runs.length > 0 && available_runs.length > 0}
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
