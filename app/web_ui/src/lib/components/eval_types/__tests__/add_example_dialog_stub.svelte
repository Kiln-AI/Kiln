<script lang="ts" context="module">
  export type GuideSample = {
    input?: string
    output?: string
    task_run_id?: string
  }
</script>

<script lang="ts">
  // Test stub for $lib/components/add_example_dialog.svelte. The real dialog
  // fetches the task schema in onMount, which never runs under the SSR-style
  // render used in these tests. This stub renders simple input/output fields
  // and dispatches the same `submit` event so wrappers (e.g.
  // ManualExampleDialog) can be tested for prop wiring and event handling.
  import { createEventDispatcher } from "svelte"

  export let project_id: string = ""
  export let task_id: string = ""
  export let existing_examples: unknown[] = []
  export let include_input: boolean = true
  export let include_output: boolean = true
  export let manual_only: boolean = false
  export let title: string | null = null
  export let sub_subtitle: string = ""
  export let submit_label: string = "Add"
  export let disable_when_empty: boolean = false

  let input_value = ""
  let output_value = ""

  const dispatch = createEventDispatcher<{
    submit: { sample: GuideSample; index: number; mode: "add" | "edit" }
  }>()

  export function open_add() {}
  export function open_edit() {}

  function add() {
    dispatch("submit", {
      sample: { input: input_value, output: output_value },
      index: -1,
      mode: "add",
    })
  }
</script>

<div
  data-testid="add-example-stub"
  data-title={title}
  data-sub-subtitle={sub_subtitle}
  data-manual-only={manual_only}
  data-submit-label={submit_label}
  data-disable-when-empty={disable_when_empty}
  data-include-input={include_input}
  data-include-output={include_output}
  data-project-id={project_id}
  data-task-id={task_id}
  data-existing-count={existing_examples.length}
>
  <textarea data-testid="stub-input" bind:value={input_value}></textarea>
  <textarea data-testid="stub-output" bind:value={output_value}></textarea>
  <button data-testid="stub-add" on:click={add}>Add</button>
</div>
