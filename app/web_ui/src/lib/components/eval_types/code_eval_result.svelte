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
          type: "code_eval"
          timeout_seconds: number
        })
      : null
</script>

<div class="flex flex-col gap-2">
  <div>
    <span class="badge badge-outline badge-sm text-xs">Beta</span>
  </div>

  <EvalResultScores {scores} {skipped_reason} {skipped_detail} />

  {#if props}
    <div class="text-xs text-gray-400 flex flex-col gap-0.5">
      <div>Timeout: {props.timeout_seconds}s</div>
    </div>
  {/if}
</div>
