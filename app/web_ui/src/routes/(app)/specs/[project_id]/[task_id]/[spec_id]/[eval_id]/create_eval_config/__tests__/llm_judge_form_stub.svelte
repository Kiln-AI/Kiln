<script lang="ts">
  import type { Eval, Task, EvalConfigType, Spec } from "$lib/types"

  export let evaluator: Eval | undefined = undefined
  export let task: Task | undefined = undefined
  export let spec: Spec | null = null
  export let task_id: string = ""
  export let model_name: string | undefined = undefined
  export let provider_name: string | undefined = undefined
  export let combined_model_name: string | undefined = undefined
  export let selected_algo: EvalConfigType | undefined = undefined

  export function getProperties(): Record<string, unknown> {
    return {}
  }

  export function getConfigType(): EvalConfigType | undefined {
    return selected_algo
  }
</script>

<div data-testid="llm-judge-form-stub">LLM Judge Form Stub</div>
