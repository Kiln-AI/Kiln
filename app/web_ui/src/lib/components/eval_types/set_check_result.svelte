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
          type: "set_check"
          expected_set?: string[] | null
          reference_key?: string | null
          value_expression?: string | null
          mode: "subset" | "superset" | "equal"
        })
      : null

  $: passed = scores.match === 1.0
  $: has_score = "match" in scores

  const mode_labels: Record<string, string> = {
    subset: "Output is subset of expected",
    superset: "Output is superset of expected",
    equal: "Output equals expected set",
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
      <div>Mode: {mode_labels[props.mode] ?? props.mode}</div>
      {#if props.expected_set != null && props.expected_set.length > 0}
        <div>
          Expected: <span class="font-mono bg-base-200 px-1 rounded"
            >{props.expected_set.join(", ")}</span
          >
        </div>
      {:else if props.reference_key != null}
        <div>
          Reference key: <span class="font-mono bg-base-200 px-1 rounded"
            >{props.reference_key}</span
          >
        </div>
      {/if}
      {#if props.value_expression}
        <div>
          Expression: <span class="font-mono bg-base-200 px-1 rounded"
            >{props.value_expression}</span
          >
        </div>
      {/if}
    </div>
  {/if}
</div>
