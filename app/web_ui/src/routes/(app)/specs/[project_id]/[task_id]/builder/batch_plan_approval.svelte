<script lang="ts">
  // Plan approval for multi-turn Step 4: review/edit one synthetic-user
  // scenario per conversation before model calls are spent driving them.
  // While the pipeline runs, the same table doubles as the live status
  // board (per-row pills), read-only.
  // Sibling of /generate's kiln_pro_batch_plan.svelte; children are shared.
  import KilnProPlanSummary from "../../../../generate/[project_id]/[task_id]/kiln_pro_plan_summary.svelte"
  import KilnProPromptsTable, {
    type RowStatusPill,
  } from "../../../../generate/[project_id]/[task_id]/kiln_pro_prompts_table.svelte"

  export let plan: { prompts: string[]; summary: string }
  export let on_approve: () => void
  export let on_regenerate: () => void
  export let on_delete_prompt: (index: number) => void
  export let on_edit_prompt: (index: number, value: string) => void
  export let summary_out_of_sync = false
  // The pipeline is streaming: hide every mutating affordance (edit, delete,
  // regenerate, drive) — the rows are live status now, not an editable plan.
  export let running = false
  // Per-row pipeline status pills, index-aligned with plan.prompts.
  export let row_statuses: RowStatusPill[] | null = null
  // Set when conversations were already driven from this plan (user navigated
  // Back from review) — offers returning to the results; driving again is
  // demoted to a secondary action since it re-spends model calls.
  export let on_continue: (() => void) | null = null
  // Renders a Back affordance (bottom-left, matching the wizard steps).
  export let on_back: (() => void) | null = null

  $: count = plan.prompts.length
</script>

<div class="flex flex-col gap-4 mt-4">
  <div class="flex flex-col md:flex-row md:items-start gap-4">
    <div class="flex-grow">
      <div class="text-xl font-bold">
        {running ? "Driving Conversations" : "Conversation Plan"}
      </div>
      <div class="text-sm font-light text-gray-500">
        <span class="font-medium text-base-content">
          {count} synthetic users
        </span>
        {#if running}
          — each conversation is driven, judged, and distilled as it completes.
        {:else}
          planned — review and edit, then drive one conversation per user.
        {/if}
      </div>
    </div>
    {#if !running}
      <div class="flex flex-row gap-2 shrink-0">
        <button class="btn btn-sm" on:click={on_regenerate}>Regenerate</button>
        <button
          class="btn btn-sm {on_continue ? '' : 'btn-primary'}"
          disabled={count === 0}
          on:click={on_approve}
        >
          Drive {count} Conversations
        </button>
        {#if on_continue}
          <button class="btn btn-sm btn-primary" on:click={on_continue}>
            Continue to Review →
          </button>
        {/if}
      </div>
    {/if}
  </div>

  {#if !running}
    <KilnProPlanSummary
      summary={plan.summary}
      out_of_sync={summary_out_of_sync}
    />
  {/if}
  <KilnProPromptsTable
    prompts={plan.prompts}
    on_delete={running ? null : on_delete_prompt}
    on_edit={running ? null : on_edit_prompt}
    start_expanded={true}
    item_label="synthetic users"
    item_label_singular="Synthetic User"
    {row_statuses}
  />

  {#if on_back && !running}
    <div>
      <button class="btn btn-ghost btn-sm" on:click={on_back}>← Back</button>
    </div>
  {/if}
</div>
