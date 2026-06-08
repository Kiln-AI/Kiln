<script lang="ts">
  import EvalResultScores from "./eval_result_scores.svelte"
  import type { EvalConfig } from "$lib/types"

  export let scores: Record<string, number> = {}
  export let skipped_reason: string | null = null
  export let skipped_detail: string | null = null
  export let eval_config: EvalConfig | null = null

  type ToolCallSpec = {
    tool_name: string
    expected_args?: Record<string, unknown> | null
  }

  $: props =
    eval_config?.properties && "type" in eval_config.properties
      ? (eval_config.properties as {
          type: "tool_call_check"
          expected_tools: ToolCallSpec[]
          match_mode: "any" | "all" | "ordered" | "never"
          on_unexpected_tools: "ignore" | "fail"
        })
      : null

  $: passed = scores.match === 1.0
  $: has_score = "match" in scores

  const match_mode_labels: Record<string, string> = {
    any: "Any expected tool called",
    all: "All expected tools called",
    ordered: "All expected tools called in order",
    never: "None of the listed tools called",
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
        Match mode: {match_mode_labels[props.match_mode] ?? props.match_mode}
      </div>
      {#if props.expected_tools.length > 0}
        <div>
          Tools: {props.expected_tools.map((t) => t.tool_name).join(", ")}
        </div>
      {/if}
      {#if props.on_unexpected_tools === "fail"}
        <div>Fails on unexpected tool calls</div>
      {/if}
    </div>
  {/if}
</div>
