<script lang="ts">
  import LlmJudgeForm from "../llm_judge_form.svelte"
  import type { JudgeAlgorithm } from "$lib/utils/eval_types/judge_algorithm"

  /**
   * Binds LlmJudgeForm's outward state so a test can watch it, the way
   * eval_config_builder does. `default_prompt_unavailable` starts true here to stand
   * in for a parent that retained it from an earlier failed fetch: Svelte 4 `bind:`
   * seeds the child from the parent, so the child's own `= false` initializer never
   * runs and only an explicit clear can undo it.
   */
  export let default_prompt_unavailable: boolean = true
  export let default_reference_keys: string[] = []
  export let model_name: string | undefined = undefined
  export let provider_name: string | undefined = undefined
  export let combined_model_name: string | undefined = undefined
  export let judge_prompt: string | undefined = undefined
  export let system_prompt: string | undefined = undefined
  export let selected_algo: JudgeAlgorithm | undefined = undefined

  let prompt_replaced_count = 0
</script>

<LlmJudgeForm
  task_id="task1"
  project_id="proj1"
  eval_id="eval1"
  {model_name}
  {provider_name}
  {combined_model_name}
  bind:judge_prompt
  bind:system_prompt
  bind:selected_algo
  bind:default_prompt_unavailable
  bind:default_reference_keys
  on:prompt_replaced={() => prompt_replaced_count++}
/>

<div data-testid="harness-prompt-unavailable">{default_prompt_unavailable}</div>
<div data-testid="harness-judge-prompt">{String(judge_prompt)}</div>
<div data-testid="harness-system-prompt">{String(system_prompt)}</div>
<div data-testid="harness-selected-algo">{String(selected_algo)}</div>
<div data-testid="harness-prompt-replaced-count">{prompt_replaced_count}</div>
<div data-testid="harness-reference-keys">
  {default_reference_keys.join(",")}
</div>
