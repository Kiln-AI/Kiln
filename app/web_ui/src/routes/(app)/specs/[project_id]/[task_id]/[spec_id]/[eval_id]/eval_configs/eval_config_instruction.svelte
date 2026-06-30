<script lang="ts">
  import type { EvalConfig, ProviderModels } from "$lib/types"
  import {
    type V2EvalType,
    type V2PropsMap,
    getV2TypeFromEvalConfig,
  } from "$lib/utils/eval_types/registry"
  import { assertNever } from "$lib/utils/exhaustive"
  import { model_info, model_name, provider_name_from_id } from "$lib/stores"
  import Output from "$lib/ui/output.svelte"

  export let eval_config: EvalConfig | null = null

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

  // Judge model/provider info for V2 llm_judge
  function getJudgeModelName(
    config: EvalConfig,
    mi: ProviderModels | null,
  ): string | null {
    const v2Type = getV2TypeFromEvalConfig(config)
    if (v2Type === "llm_judge") {
      const props = getV2Props(config, "llm_judge")
      if (props?.model_name) return model_name(props.model_name, mi)
      return null
    }
    if (
      config.config_type === "g_eval" ||
      config.config_type === "llm_as_judge"
    ) {
      if (config.model_name) return model_name(config.model_name, mi)
      return null
    }
    return null
  }

  function getJudgeProvider(config: EvalConfig): string | null {
    const v2Type = getV2TypeFromEvalConfig(config)
    if (v2Type === "llm_judge") {
      const props = getV2Props(config, "llm_judge")
      if (props?.model_provider)
        return provider_name_from_id(props.model_provider)
      return null
    }
    if (
      config.config_type === "g_eval" ||
      config.config_type === "llm_as_judge"
    ) {
      if (config.model_provider)
        return provider_name_from_id(config.model_provider)
      return null
    }
    return null
  }

  function isGEval(config: EvalConfig): boolean {
    const v2Type = getV2TypeFromEvalConfig(config)
    if (v2Type === "llm_judge") {
      const props = getV2Props(config, "llm_judge")
      return props?.g_eval === true
    }
    return config.config_type === "g_eval"
  }

  function isJudgeEval(config: EvalConfig): boolean {
    const v2Type = getV2TypeFromEvalConfig(config)
    if (v2Type === "llm_judge") return true
    return (
      config.config_type === "g_eval" || config.config_type === "llm_as_judge"
    )
  }

  // Reactive V2 type
  $: v2Type = eval_config ? getV2TypeFromEvalConfig(eval_config) : null
</script>

{#if eval_config}
  <div class="text-sm" data-testid="eval-config-instruction">
    {#if isJudgeEval(eval_config)}
      {@const judgeModel = getJudgeModelName(eval_config, $model_info)}
      {@const judgeProvider = getJudgeProvider(eval_config)}
      {#if judgeModel}
        <div data-testid="judge-model-line">
          <span class="font-medium">Judge Model:</span>
          {judgeModel}
        </div>
      {/if}
      {#if judgeProvider}
        <div data-testid="judge-provider-line">
          <span class="font-medium">Provider:</span>
          {judgeProvider}
        </div>
      {/if}
      {#if isGEval(eval_config)}
        <div data-testid="judge-method-line">
          <span class="font-medium">Method:</span> G-Eval
        </div>
      {/if}
    {/if}

    {#if v2Type}
      {#if v2Type === "llm_judge"}
        {@const props = getV2Props(eval_config, "llm_judge")}
        {#if props?.prompt_template}
          <div class="mt-2">
            <div class="font-medium mb-1">Judge Prompt</div>
            <Output raw_output={props.prompt_template} max_height="200px" />
          </div>
        {/if}
        {#if props?.system_prompt}
          <div class="mt-2">
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
        <div class="my-2">
          <span class="font-medium">Task Description:</span>
          <Output raw_output={task_desc} max_height="200px" />
        </div>
      {/if}
      {#if eval_steps}
        <div>
          <span class="font-medium">Evaluation Steps:</span>
          {#each eval_steps as step}
            <Output raw_output={step} max_height="200px" />
          {/each}
        </div>
      {/if}
      {#if !task_desc && !eval_steps}
        <div class="text-gray-500">No details available.</div>
      {/if}
    {/if}
  </div>
{/if}
