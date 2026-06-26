<script lang="ts">
  import EvalResultScores from "./eval_result_scores.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { EvalConfig } from "$lib/types"
  import { model_info, model_name } from "$lib/stores"
  import { extractV2Props } from "$lib/utils/eval_types/registry"

  export let scores: Record<string, number> = {}
  export let skipped_reason: string | null = null
  export let skipped_detail: string | null = null
  export let eval_config: EvalConfig | null = null
  export let intermediate_outputs: Record<string, string> | null = null

  $: props = extractV2Props(eval_config, "llm_judge")
  $: reasoning =
    intermediate_outputs?.reasoning ||
    intermediate_outputs?.chain_of_thought ||
    null

  let reasoning_dialog: Dialog | null = null
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
      {#if reasoning}
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
  {:else if reasoning}
    <div class="text-xs text-gray-400">
      <button
        class="text-xs link link-hover text-gray-400"
        on:click={() => reasoning_dialog?.show()}
      >
        View reasoning
      </button>
    </div>
  {/if}
</div>

<Dialog
  bind:this={reasoning_dialog}
  title="Judge Reasoning"
  action_buttons={[
    {
      label: "Close",
      isCancel: true,
    },
  ]}
>
  <div class="font-light text-sm whitespace-pre-wrap">
    {reasoning}
  </div>
</Dialog>
