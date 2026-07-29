<script lang="ts">
  import KilnProPlanSummary from "./kiln_pro_plan_summary.svelte"
  import KilnProPromptsTable from "./kiln_pro_prompts_table.svelte"

  export let plan: { prompts: string[]; summary: string }
  export let on_generate_inputs: () => void
  export let on_regenerate: () => void
  export let on_delete_prompt: (index: number) => void
  export let summary_out_of_sync = false
  // Optional override for the generate button's label. The eval builder's
  // click starts a full conversation drive (long, paid), not quick sample
  // generation — its label must say so. Default keeps /generate unchanged.
  export let generate_button_label: string | null = null
  // The eval builder hides the generate button once the exact current plan
  // already has driven results — continuing to those results is the only
  // forward action there. Default keeps /generate unchanged.
  export let hide_generate_button = false

  $: count = plan.prompts.length

  // No confirm here — each parent decides whether and when regenerating
  // needs confirmation (e.g. before discarding driven results).
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
      <button class="btn btn-md" on:click={on_regenerate}>New Batch Plan</button
      >
      {#if !hide_generate_button}
        <button
          class="btn btn-md btn-primary"
          disabled={count === 0}
          on:click={on_generate_inputs}
        >
          {generate_button_label ?? `Generate Batch (${count})`}
        </button>
      {/if}
    </div>
  </div>

  <KilnProPlanSummary
    summary={plan.summary}
    out_of_sync={summary_out_of_sync}
  />
  <KilnProPromptsTable prompts={plan.prompts} on_delete={on_delete_prompt} />
</div>
