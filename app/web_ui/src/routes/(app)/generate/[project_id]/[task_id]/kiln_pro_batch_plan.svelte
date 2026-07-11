<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import KilnProPlanSummary from "./kiln_pro_plan_summary.svelte"
  import KilnProPromptsTable from "./kiln_pro_prompts_table.svelte"

  export let plan: { prompts: string[]; summary: string }
  export let on_generate_inputs: () => void
  export let on_regenerate: () => void
  export let on_delete_prompt: (index: number) => void
  export let summary_out_of_sync = false

  $: count = plan.prompts.length

  // Starting a new plan throws away this one (and any items the user trimmed),
  // so confirm first — same pattern as clearing a synth session.
  let new_plan_dialog: Dialog | null = null
</script>

<div class="flex flex-col gap-4 mt-12">
  <div class="flex flex-col md:flex-row md:items-start gap-4">
    <div class="flex-grow">
      <div class="text-2xl font-bold">Batch Plan</div>
      <div class="text-sm font-light text-gray-500">
        Review the plan for generating your synthetic data batch.
      </div>
    </div>
    <div class="flex flex-row gap-2 shrink-0">
      <button class="btn btn-md" on:click={() => new_plan_dialog?.show()}
        >New Batch Plan</button
      >
      <button
        class="btn btn-md btn-primary"
        disabled={count === 0}
        on:click={on_generate_inputs}
      >
        Generate Inputs ({count})
      </button>
    </div>
  </div>

  <KilnProPlanSummary
    summary={plan.summary}
    out_of_sync={summary_out_of_sync}
  />
  <KilnProPromptsTable prompts={plan.prompts} on_delete={on_delete_prompt} />
</div>

<Dialog
  title="New Batch Plan?"
  bind:this={new_plan_dialog}
  action_buttons={[
    {
      label: "Keep Current Plan",
      isCancel: true,
    },
    {
      label: "New Plan (Discard Current)",
      isWarning: true,
      action: () => {
        on_regenerate()
        return true
      },
    },
  ]}
>
  <div class="font-light flex flex-col gap-2">
    <p>
      This discards the current plan{summary_out_of_sync
        ? ", including the dataset items you removed"
        : ""}, and takes you back to set up a new one.
    </p>
    <Warning warning_message="This action cannot be undone." />
  </div>
</Dialog>
