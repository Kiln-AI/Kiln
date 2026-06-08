<script lang="ts">
  import EvalResultScores from "./eval_result_scores.svelte"
  import type { EvalConfig } from "$lib/types"
  import { model_info, model_name } from "$lib/stores"

  export let scores: Record<string, number> = {}
  export let skipped_reason: string | null = null
  export let skipped_detail: string | null = null
  export let eval_config: EvalConfig | null = null

  $: props =
    eval_config?.properties && "type" in eval_config.properties
      ? (eval_config.properties as {
          type: "llm_judge"
          model_name: string
          model_provider: string
          g_eval: boolean
        })
      : null
</script>

<div class="flex flex-col gap-2">
  <EvalResultScores {scores} {skipped_reason} {skipped_detail} />

  {#if props}
    <div class="text-xs text-gray-400 flex flex-col gap-0.5">
      <div>
        Model: {model_name(props.model_name, $model_info)}
      </div>
      {#if props.g_eval}
        <div class="flex items-center gap-1">
          <span class="badge badge-outline badge-xs">G-Eval</span>
          Chain-of-thought scoring
        </div>
      {/if}
    </div>
  {/if}
</div>
