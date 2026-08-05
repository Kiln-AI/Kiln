<script lang="ts" context="module">
  import type { EvalConfigType } from "$lib/types"

  let _initial_selected_algo: EvalConfigType | undefined = undefined
  let _initial_combined_model_name: string | undefined = undefined
  let _initial_model_name: string | undefined = undefined
  let _initial_provider_name: string | undefined = undefined
  let _initial_judge_prompt: string | undefined = undefined

  export function setInitialLlmJudgeValues(values: {
    selected_algo?: EvalConfigType
    combined_model_name?: string
    model_name?: string
    provider_name?: string
    judge_prompt?: string
  }) {
    _initial_selected_algo = values.selected_algo
    _initial_combined_model_name = values.combined_model_name
    _initial_model_name = values.model_name
    _initial_provider_name = values.provider_name
    _initial_judge_prompt = values.judge_prompt
  }

  export function resetInitialLlmJudgeValues() {
    _initial_selected_algo = undefined
    _initial_combined_model_name = undefined
    _initial_model_name = undefined
    _initial_provider_name = undefined
    _initial_judge_prompt = undefined
  }
</script>

<script lang="ts">
  export let task_id: string = ""
  export let project_id: string = ""
  export let eval_id: string = ""
  export let model_name: string | undefined = _initial_model_name
  export let provider_name: string | undefined = _initial_provider_name
  export let combined_model_name: string | undefined =
    _initial_combined_model_name
  export let selected_algo: EvalConfigType | undefined = _initial_selected_algo
  export let judge_prompt: string | undefined = _initial_judge_prompt
  export let system_prompt: string | undefined = undefined

  // Force-push initial values via reactive assignment so bind: propagates
  // them to the parent. In Svelte 4, bind: sends the parent's initial
  // value DOWN, overriding the child's default. This reactive block runs
  // after initial render and pushes the configured values back UP.
  let _applied = false
  $: if (!_applied) {
    _applied = true
    if (_initial_model_name !== undefined) model_name = _initial_model_name
    if (_initial_provider_name !== undefined)
      provider_name = _initial_provider_name
    if (_initial_combined_model_name !== undefined)
      combined_model_name = _initial_combined_model_name
    if (_initial_selected_algo !== undefined)
      selected_algo = _initial_selected_algo
    if (_initial_judge_prompt !== undefined)
      judge_prompt = _initial_judge_prompt
  }
</script>

<div data-testid="llm-judge-form-stub">LLM Judge Form Stub</div>
