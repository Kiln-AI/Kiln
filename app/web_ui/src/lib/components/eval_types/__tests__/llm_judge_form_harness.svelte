<script lang="ts">
  import LlmJudgeForm from "../llm_judge_form.svelte"

  /**
   * Binds LlmJudgeForm's outward state so a test can watch it, the way
   * eval_config_builder does. `default_prompt_unavailable` starts true here to stand
   * in for a parent that retained it from an earlier failed fetch: Svelte 4 `bind:`
   * seeds the child from the parent, so the child's own `= false` initializer never
   * runs and only an explicit clear can undo it.
   */
  export let default_prompt_unavailable: boolean = true
  export let default_reference_keys: string[] = []
</script>

<LlmJudgeForm
  task_id="task1"
  project_id="proj1"
  eval_id="eval1"
  bind:default_prompt_unavailable
  bind:default_reference_keys
/>

<div data-testid="harness-prompt-unavailable">{default_prompt_unavailable}</div>
<div data-testid="harness-reference-keys">
  {default_reference_keys.join(",")}
</div>
