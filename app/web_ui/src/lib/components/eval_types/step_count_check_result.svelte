<script lang="ts">
  import EvalResultScores from "./eval_result_scores.svelte"
  import type { EvalConfig } from "$lib/types"

  export let scores: Record<string, number> = {}
  export let skipped_reason: string | null = null
  export let skipped_detail: string | null = null
  export let eval_config: EvalConfig | null = null

  $: props =
    eval_config?.properties && "type" in eval_config.properties
      ? (eval_config.properties as {
          type: "step_count_check"
          count_type: "tool_calls" | "model_responses" | "turns"
          min_count?: number | null
          max_count?: number | null
        })
      : null

  $: passed = scores.match === 1.0
  $: has_score = "match" in scores

  const count_type_labels: Record<string, string> = {
    tool_calls: "Tool calls",
    model_responses: "Model responses",
    turns: "Turns",
  }

  function format_bounds(
    min: number | null | undefined,
    max: number | null | undefined,
  ): string {
    if (min != null && max != null) return `${min} - ${max}`
    if (min != null) return `at least ${min}`
    if (max != null) return `at most ${max}`
    return "any"
  }
</script>

<div class="flex flex-col gap-2">
  {#if has_score && !skipped_reason}
    <div>
      {#if passed}
        <span class="badge badge-success badge-sm gap-1">
          <i class="bi bi-check-circle-fill text-xs"></i>
          Pass
        </span>
      {:else}
        <span class="badge badge-error badge-sm gap-1">
          <i class="bi bi-x-circle-fill text-xs"></i>
          Fail
        </span>
      {/if}
    </div>
  {/if}

  <EvalResultScores {scores} {skipped_reason} {skipped_detail} />

  {#if props}
    <div class="text-xs text-gray-400 flex flex-col gap-0.5">
      <div>
        Counting: {count_type_labels[props.count_type] ?? props.count_type}
      </div>
      <div>
        Allowed range: {format_bounds(props.min_count, props.max_count)}
      </div>
    </div>
  {/if}
</div>
