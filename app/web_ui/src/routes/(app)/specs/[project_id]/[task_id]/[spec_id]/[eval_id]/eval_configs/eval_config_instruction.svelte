<script lang="ts">
  import type { EvalConfig } from "$lib/types"
  import {
    type V2EvalType,
    type V2PropsMap,
    getV2TypeFromEvalConfig,
    evalTypeJudgeLabel,
  } from "$lib/utils/eval_types/registry"
  import { assertNever } from "$lib/utils/exhaustive"

  export let eval_config: EvalConfig | null = null

  // Type line label
  function typeLabel(config: EvalConfig): string {
    const v2Type = getV2TypeFromEvalConfig(config)
    if (v2Type) {
      return evalTypeJudgeLabel(v2Type)
    }
    if (config.config_type === "g_eval") return "G-Eval"
    if (config.config_type === "llm_as_judge") return "LLM as Judge"
    return config.config_type
  }

  // Legacy helpers
  function get_eval_steps(config: EvalConfig): string[] | undefined {
    if (!config?.properties) return undefined
    const props = config.properties as Record<string, unknown>
    if (!props["eval_steps"]) return undefined
    if (!Array.isArray(props["eval_steps"])) return undefined
    return props["eval_steps"] as string[]
  }

  function get_task_description(config: EvalConfig): string | undefined {
    if (!config?.properties) return undefined
    const props = config.properties as Record<string, unknown>
    return (props["task_description"] as string) || undefined
  }

  // V2 helpers
  function getV2Props<T extends V2EvalType>(
    config: EvalConfig,
    _: T,
  ): V2PropsMap[T] | null {
    if (!config?.properties) return null
    return config.properties as V2PropsMap[T]
  }

  function valueExpressionLabel(expr: string | null | undefined): string {
    if (!expr) return "output"
    return expr
  }

  // Reactive V2 type
  $: v2Type = eval_config ? getV2TypeFromEvalConfig(eval_config) : null
</script>

{#if eval_config}
  <div class="text-sm" data-testid="eval-config-instruction">
    <div class="mb-1">
      <span class="font-medium">Type:</span>
      <span data-testid="eval-config-type-label">{typeLabel(eval_config)}</span>
    </div>

    {#if v2Type}
      {#if v2Type === "llm_judge"}
        {@const props = getV2Props(eval_config, "llm_judge")}
        {#if props?.prompt_template}
          <div class="whitespace-pre-line">{props.prompt_template}</div>
        {/if}
        {#if props?.system_prompt}
          <div class="mt-1">
            <span class="font-medium">System prompt:</span>
            <span class="whitespace-pre-line">{props.system_prompt}</span>
          </div>
        {/if}
        {#if !props?.prompt_template && !props?.system_prompt}
          <div class="text-gray-500">No details available.</div>
        {/if}
      {:else if v2Type === "code_eval"}
        {@const props = getV2Props(eval_config, "code_eval")}
        {#if props?.code}
          <pre
            class="font-mono text-xs bg-base-200 rounded p-2 mt-1 overflow-x-auto whitespace-pre"
            data-testid="code-eval-pre">{props.code}</pre>
        {:else}
          <div class="text-gray-500">No code provided.</div>
        {/if}
      {:else if v2Type === "exact_match"}
        {@const props = getV2Props(eval_config, "exact_match")}
        {#if props}
          {@const source = valueExpressionLabel(props.value_expression)}
          {@const casePart = props.case_sensitive ? "" : " (case-insensitive)"}
          <div>
            {#if props.expected_value != null}
              Compare <span class="font-medium">{source}</span> to expected
              value
              <span class="font-medium">"{props.expected_value}"</span
              >{casePart}
            {:else if props.reference_key}
              Compare <span class="font-medium">{source}</span> to
              <span class="font-medium"
                >reference_data.{props.reference_key}</span
              >{casePart}
            {:else}
              Exact match on <span class="font-medium">{source}</span>{casePart}
            {/if}
          </div>
        {:else}
          <div class="text-gray-500">No details available.</div>
        {/if}
      {:else if v2Type === "pattern_match"}
        {@const props = getV2Props(eval_config, "pattern_match")}
        {#if props}
          {@const source = valueExpressionLabel(props.value_expression)}
          {@const modeLabel =
            props.mode === "must_not_match" ? "must not match" : "must match"}
          <div>
            <span class="font-medium">{source}</span>
            {modeLabel} pattern
            <span class="font-medium font-mono">/{props.pattern}/</span>
          </div>
        {:else}
          <div class="text-gray-500">No details available.</div>
        {/if}
      {:else if v2Type === "contains"}
        {@const props = getV2Props(eval_config, "contains")}
        {#if props}
          {@const source = valueExpressionLabel(props.value_expression)}
          {@const modeLabel =
            props.mode === "must_not_contain"
              ? "must not contain"
              : "must contain"}
          {@const casePart = props.case_sensitive ? "" : " (case-insensitive)"}
          <div>
            <span class="font-medium">{source}</span>
            {modeLabel}
            {#if props.substring != null}
              <span class="font-medium">"{props.substring}"</span>
            {:else if props.reference_key}
              <span class="font-medium"
                >reference_data.{props.reference_key}</span
              >
            {:else}
              a value
            {/if}{casePart}
          </div>
        {:else}
          <div class="text-gray-500">No details available.</div>
        {/if}
      {:else if v2Type === "set_check"}
        {@const props = getV2Props(eval_config, "set_check")}
        {#if props}
          {@const source = valueExpressionLabel(props.value_expression)}
          {@const modeLabels = {
            subset: "is a subset of",
            superset: "is a superset of",
            equal: "equals",
          }}
          {@const modeLabel = modeLabels[props.mode] || props.mode}
          <div>
            <span class="font-medium">{source}</span>
            {modeLabel}
            {#if props.expected_set && props.expected_set.length > 0}
              <span class="font-medium"
                >{"{" + props.expected_set.join(", ") + "}"}</span
              >
            {:else if props.reference_key}
              <span class="font-medium"
                >reference_data.{props.reference_key}</span
              >
            {:else}
              a set
            {/if}
          </div>
        {:else}
          <div class="text-gray-500">No details available.</div>
        {/if}
      {:else if v2Type === "tool_call_check"}
        {@const props = getV2Props(eval_config, "tool_call_check")}
        {#if props}
          {@const toolNames = props.expected_tools.map((t) => t.tool_name)}
          {@const modeLabels = {
            any: "any of",
            all: "all of",
            ordered: "in order",
            never: "never call",
          }}
          {@const modeLabel = modeLabels[props.match_mode] || props.match_mode}
          <div>
            Expect <span class="font-medium">{modeLabel}</span>:
            <span class="font-medium">{toolNames.join(", ")}</span>
            {#if props.on_unexpected_tools === "fail"}
              <span class="text-gray-500">(fail on unexpected tools)</span>
            {/if}
          </div>
        {:else}
          <div class="text-gray-500">No details available.</div>
        {/if}
      {:else if v2Type === "step_count_check"}
        {@const props = getV2Props(eval_config, "step_count_check")}
        {#if props}
          {@const typeLabels = {
            tool_calls: "tool calls",
            model_responses: "model responses",
            turns: "turns",
          }}
          {@const countLabel = typeLabels[props.count_type] || props.count_type}
          <div>
            Count <span class="font-medium">{countLabel}</span
            >{#if props.min_count != null || props.max_count != null}:
              {#if props.min_count != null}
                min <span class="font-medium">{props.min_count}</span
                >{#if props.max_count != null},{/if}
              {/if}
              {#if props.max_count != null}
                max <span class="font-medium">{props.max_count}</span>
              {/if}
            {/if}
          </div>
        {:else}
          <div class="text-gray-500">No details available.</div>
        {/if}
      {:else}
        {assertNever(v2Type)}
      {/if}
    {:else}
      {@const task_desc = get_task_description(eval_config)}
      {@const eval_steps = get_eval_steps(eval_config)}
      {#if task_desc}
        <div class="mb-2">
          <span class="font-medium">Task Description:</span>
          {task_desc}
        </div>
      {/if}
      {#if eval_steps}
        <div>
          <span class="font-medium">Steps:</span>
          <ol class="list-decimal pl-5">
            {#each eval_steps as step}
              <li>
                <span class="whitespace-pre-line">{step}</span>
              </li>
            {/each}
          </ol>
        </div>
      {/if}
      {#if !task_desc && !eval_steps}
        <div class="text-gray-500">No details available.</div>
      {/if}
    {/if}
  </div>
{/if}
