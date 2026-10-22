<script lang="ts">
  import EvalResultScores from "./eval_result_scores.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import JudgeTraceLink from "./judge_trace_link.svelte"
  import type { EvalConfig, Trace } from "$lib/types"
  import { model_info, model_name } from "$lib/stores"
  import { extractV2Props } from "$lib/utils/eval_types/registry"

  export let scores: Record<string, number> = {}
  export let score_labels: Record<string, string> = {}
  export let skipped_reason: string | null = null
  export let skipped_detail: string | null = null
  export let eval_config: EvalConfig | null = null
  export let intermediate_outputs: Record<string, string> | null = null
  /** Fetches the judge's conversation. Null when the run saved none. */
  export let load_judge_trace: (() => Promise<Trace | null>) | null = null

  $: props = extractV2Props(eval_config, "llm_judge")
  $: reasoning =
    intermediate_outputs?.reasoning ||
    intermediate_outputs?.chain_of_thought ||
    null

  let reasoning_dialog: Dialog | null = null
</script>

<div class="flex flex-col gap-2">
  <EvalResultScores {scores} {score_labels} {skipped_reason} {skipped_detail} />

  {#if props || reasoning || load_judge_trace}
    <div class="text-xs text-gray-400 flex flex-col gap-0.5">
      {#if props}
        <div>
          Model: {model_name(props.model_name, $model_info)}
        </div>
        {#if props.g_eval}
          <div class="flex items-center gap-1">
            <span class="badge badge-outline badge-xs">G-Eval</span>
            Chain-of-thought scoring
          </div>
        {/if}
        {#if props.trace_toolset_version != null}
          <div class="flex items-center gap-1">
            <span class="badge badge-outline badge-xs">Agentic Judge</span>
            Reads the trace with tools
          </div>
        {/if}
      {/if}
      {#if load_judge_trace}
        <div>
          <JudgeTraceLink load_trace={load_judge_trace} />
        </div>
      {:else if reasoning}
        <div>
          <button
            class="text-xs link link-hover text-gray-400"
            on:click={() => reasoning_dialog?.show()}
          >
            View reasoning
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>

<Dialog bind:this={reasoning_dialog} title="Judge Reasoning">
  <div class="font-light text-sm whitespace-pre-wrap">
    {reasoning}
  </div>
</Dialog>
