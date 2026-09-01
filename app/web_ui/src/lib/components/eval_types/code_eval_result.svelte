<script lang="ts">
  import EvalResultScores from "./eval_result_scores.svelte"
  import type { EvalConfig } from "$lib/types"
  import { extractV2Props } from "$lib/utils/eval_types/registry"

  export let scores: Record<string, number> = {}
  export let skipped_reason: string | null = null
  export let skipped_detail: string | null = null
  export let eval_config: EvalConfig | null = null

  $: props = extractV2Props(eval_config, "code_eval")
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
