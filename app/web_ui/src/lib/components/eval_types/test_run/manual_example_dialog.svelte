<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import AddExampleDialog, {
    type GuideSample,
  } from "$lib/components/add_example_dialog.svelte"
  import type { TaskRunOutput } from "$lib/types"

  export let project_id: string
  export let task_id: string

  let dialog: AddExampleDialog

  const dispatch = createEventDispatcher<{
    confirm: TaskRunOutput
  }>()

  export function show() {
    dialog?.open_add()
  }

  function handle_submit(
    e: CustomEvent<{
      sample: GuideSample
      index: number
      mode: "add" | "edit"
    }>,
  ) {
    const input = e.detail.sample.input ?? ""
    const output = e.detail.sample.output ?? ""
    // Guard against an empty submission — the shared dialog always closes on
    // submit, so treat both-empty as a no-op rather than dispatching a run
    // with nothing to test.
    if (!input.trim() && !output.trim()) {
      return
    }

    const ephemeral_run = {
      v: 1,
      input,
      output: {
        v: 1,
        output,
        source: { type: "human" as const, properties: {} },
        model_type: "manual",
      },
      tags: [] as string[],
      model_type: "manual",
    } satisfies TaskRunOutput

    dispatch("confirm", ephemeral_run)
  }
</script>

<AddExampleDialog
  bind:this={dialog}
  {project_id}
  {task_id}
  manual_only={true}
  title="Add Manual Example"
  sub_subtitle="Create a temporary input/output pair to test this scorer. This example won't be saved to your dataset."
  submit_label="Use Example"
  disable_when_empty={true}
  on:submit={handle_submit}
/>
