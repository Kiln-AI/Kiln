<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import ManualExampleDialog from "./manual_example_dialog.svelte"
  import TaskRunPicker from "$lib/utils/task_run_picker.svelte"
  import type { TaskRun, TaskRunOutput } from "$lib/types"

  export let project_id: string
  export let task_id: string
  export let available_runs: TaskRunOutput[] = []
  export let manual_example_supported: boolean = true

  let dialog: Dialog
  let manual_dialog: ManualExampleDialog

  const dispatch = createEventDispatcher<{
    select: TaskRunOutput
  }>()

  export function show() {
    dialog?.show()
  }

  function select_run(run: TaskRun | TaskRunOutput) {
    dispatch("select", run as TaskRunOutput)
    dialog?.close()
  }

  function handle_manual_confirm(e: CustomEvent<TaskRunOutput>) {
    dispatch("select", e.detail)
    dialog?.close()
  }
</script>

<Dialog
  bind:this={dialog}
  title="Choose Dataset Sample"
  sub_subtitle="Pick a dataset item to test this scorer against."
  width="wide"
>
  <div class="flex flex-col gap-4">
    <TaskRunPicker {available_runs} on:select={(e) => select_run(e.detail)} />
    {#if manual_example_supported}
      <div class="flex flex-row gap-1 justify-end">
        <span class="text-sm text-gray-500">or</span>
        <button
          class="link underline text-sm text-gray-500"
          on:click={() => manual_dialog?.show()}
        >
          Add Manual Example
        </button>
      </div>
    {/if}
  </div>
</Dialog>

<ManualExampleDialog
  bind:this={manual_dialog}
  {project_id}
  {task_id}
  on:confirm={handle_manual_confirm}
/>
