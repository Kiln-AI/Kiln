<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { TaskRunOutput } from "$lib/types"

  let dialog: Dialog
  let input_value = ""
  let output_value = ""

  $: both_empty = !input_value.trim() && !output_value.trim()

  const dispatch = createEventDispatcher<{
    confirm: TaskRunOutput
  }>()

  export function show() {
    input_value = ""
    output_value = ""
    dialog?.show()
  }

  function handle_confirm() {
    const ephemeral_run = {
      v: 1,
      input: input_value,
      output: {
        v: 1,
        output: output_value,
        source: { type: "human" as const, properties: {} },
        model_type: "manual",
      },
      tags: [] as string[],
      model_type: "manual",
    } satisfies TaskRunOutput

    dispatch("confirm", ephemeral_run)
    dialog?.close()
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  title="Add Manual Example"
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Use Example",
      isPrimary: true,
      disabled: both_empty,
      action: handle_confirm,
    },
  ]}
>
  <div class="flex flex-col gap-4">
    <p class="text-sm text-gray-500">
      Create a temporary input/output pair to test this scorer. This example
      won't be saved to your dataset.
    </p>
    <div class="form-control">
      <label for="manual-input" class="label">
        <span class="label-text text-sm font-medium">Input</span>
      </label>
      <textarea
        id="manual-input"
        class="textarea textarea-bordered w-full font-mono text-sm"
        rows="4"
        placeholder="Enter the task input..."
        bind:value={input_value}
        data-testid="manual-input"
      ></textarea>
    </div>
    <div class="form-control">
      <label for="manual-output" class="label">
        <span class="label-text text-sm font-medium">Output</span>
      </label>
      <textarea
        id="manual-output"
        class="textarea textarea-bordered w-full font-mono text-sm"
        rows="4"
        placeholder="Enter the model output..."
        bind:value={output_value}
        data-testid="manual-output"
      ></textarea>
    </div>
  </div>
</Dialog>
