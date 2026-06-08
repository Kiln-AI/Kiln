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
          type: "contains"
          substring?: string | null
          reference_key?: string | null
          value_expression?: string | null
          case_sensitive: boolean
          mode: "must_contain" | "must_not_contain"
        })
      : null

  $: passed = scores.match === 1.0
  $: has_score = "match" in scores

  function format_mode(mode: string): string {
    return mode === "must_contain" ? "Must contain" : "Must not contain"
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
      <div>Mode: {format_mode(props.mode)}</div>
      {#if props.substring != null}
        <div>
          Substring: <span class="font-mono bg-base-200 px-1 rounded"
            >{props.substring}</span
          >
        </div>
      {:else if props.reference_key != null}
        <div>
          Reference key: <span class="font-mono bg-base-200 px-1 rounded"
            >{props.reference_key}</span
          >
        </div>
      {/if}
      {#if !props.case_sensitive}
        <div>Case insensitive</div>
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
