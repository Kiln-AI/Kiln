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
  // Renders the generate button as an outline primary. The eval builder turns
  // this on for the screens where another solid primary is already on the
  // page, so only one solid primary shows at a time. Default keeps /generate
  // unchanged.
  export let generate_button_outline = false
  // Header, its sub-line, and the regenerate button label. Defaults equal the
  // /generate strings so that surface renders unchanged; the eval builder
  // overrides all three (it plans "scenarios", not a "batch").
  export let header_label = "Batch Plan"
  export let subheader =
    "Review the plan for generating your synthetic data batch."
  export let regenerate_label = "New Batch Plan"

  $: count = plan.prompts.length

  // No confirm here — each parent decides whether and when regenerating
  // needs confirmation (e.g. before discarding driven results).
</script>

<div class="flex flex-col gap-4 mt-12">
  <div class="flex flex-col md:flex-row md:items-start gap-4">
    <div class="flex-grow">
      <div class="text-2xl font-bold">{header_label}</div>
      <div class="text-sm font-light text-gray-500">
        {subheader}
      </div>
    </div>
    <div class="flex flex-row gap-2 shrink-0">
      <button class="btn btn-md" on:click={on_regenerate}
        >{regenerate_label}</button
      >
      {#if !hide_generate_button}
        <button
          class="btn btn-md {generate_button_outline
            ? 'btn-outline btn-primary'
            : 'btn-primary'}"
          disabled={count === 0}
          on:click={on_generate_inputs}
        >
          {generate_button_label ?? `Generate Batch (${count})`}
        </button>
      {/if}
    </div>
  </div>
  <!-- Optional per-consumer secondary action (the eval builder's
  model-settings link), right-aligned under the primary-button cluster.
  Guarded so with no consumer filling the slot NOTHING renders and
  /generate's output stays byte-identical. -->
  {#if $$slots.advanced}
    <div class="flex justify-end -mt-3">
      <slot name="advanced" />
    </div>
  {/if}

  <KilnProPlanSummary
    summary={plan.summary}
    out_of_sync={summary_out_of_sync}
  />
  <KilnProPromptsTable prompts={plan.prompts} on_delete={on_delete_prompt} />
</div>
