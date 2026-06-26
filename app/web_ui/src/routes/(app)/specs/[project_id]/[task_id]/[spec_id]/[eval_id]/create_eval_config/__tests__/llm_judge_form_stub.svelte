<script lang="ts">
  import type { EvalConfigType } from "$lib/types"

  export let task_id: string = ""
  export let model_name: string | undefined = undefined
  export let provider_name: string | undefined = undefined
  export let combined_model_name: string | undefined = undefined
  export let selected_algo: EvalConfigType | undefined = undefined
</script>

<div data-testid="llm-judge-form-stub">LLM Judge Form Stub</div>
