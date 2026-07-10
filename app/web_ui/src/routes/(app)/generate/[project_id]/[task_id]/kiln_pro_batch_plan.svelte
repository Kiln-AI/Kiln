<script lang="ts">
  import KilnProPlanSummary from "./kiln_pro_plan_summary.svelte"
  import KilnProPromptsTable from "./kiln_pro_prompts_table.svelte"

  export let plan: { prompts: string[]; summary: string }
  export let on_generate_inputs: () => void
  export let on_regenerate: () => void
  export let on_delete_prompt: (index: number) => void
  export let summary_out_of_sync = false

  $: count = plan.prompts.length
</script>

<div class="flex flex-col gap-4 mt-4">
  <div class="flex flex-col md:flex-row md:items-start gap-4">
    <div class="flex-grow">
      <div class="text-xl font-bold">Batch Plan</div>
      <div class="text-sm font-light text-gray-500">
        <span class="font-medium text-base-content">{count} prompts</span> ready
        — review and trim, then generate inputs.
      </div>
    </div>
    <div class="flex flex-row gap-2 shrink-0">
      <button class="btn btn-sm" on:click={on_regenerate}
        >Regenerate Plan</button
      >
      <button
        class="btn btn-sm btn-primary"
        disabled={count === 0}
        on:click={on_generate_inputs}
      >
        Generate {count} Inputs
      </button>
    </div>
  </div>

  <KilnProPlanSummary
    summary={plan.summary}
    out_of_sync={summary_out_of_sync}
  />
  <KilnProPromptsTable prompts={plan.prompts} on_delete={on_delete_prompt} />
</div>
