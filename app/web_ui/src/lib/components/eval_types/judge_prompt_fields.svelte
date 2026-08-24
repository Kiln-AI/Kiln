<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { SHOW_REFERENCE_DATA_UI } from "$lib/utils/eval_types/reference_data_ui"

  export let judge_prompt: string | undefined = undefined
  export let system_prompt: string | undefined = undefined
  export let prompt_fetch_error: string | null = null
  // Whether the template uses the {{ judge_instructions }} variable (evals
  // whose steps come from the Evaluation Instructions field above).
  export let show_judge_instructions_variable: boolean = false
</script>

<div class="flex flex-col gap-2">
  <p class="text-xs text-gray-500 font-medium">
    Customizing the judge prompt can improve eval quality. We've pre-filled a
    default based on your task{show_judge_instructions_variable
      ? ""
      : " and spec"}.
  </p>
  <p class="text-xs text-gray-500">
    The judge prompt is in Jinja2 format and may contain the following
    variables:
  </p>
  <ul class="text-xs text-gray-500 list-disc list-inside mb-2 indent-2">
    <li>
      <span class="font-mono font-bold">{"{{ task_input }}"}</span> The input to
      the task.
    </li>
    <li>
      <span class="font-mono font-bold">{"{{ final_message }}"}</span> The final
      message from the model.
    </li>
    <li>
      <span class="font-mono font-bold">{"{{ trace }}"}</span> The entire trace.
    </li>
    {#if show_judge_instructions_variable}
      <li>
        <span class="font-mono font-bold">{"{{ judge_instructions }}"}</span> The
        evaluation instructions above, as numbered steps.
      </li>
    {/if}
    {#if SHOW_REFERENCE_DATA_UI}
      <li>
        <span class="font-mono font-bold">{"{{ reference_data }}"}</span> Reference
        data attached to the eval case.
      </li>
    {/if}
  </ul>
</div>
{#if prompt_fetch_error}
  <div class="text-xs text-warning mb-2">{prompt_fetch_error}</div>
{/if}
<FormElement
  inputType="textarea"
  id="judge_prompt"
  label="Judge Prompt"
  bind:value={judge_prompt}
  height="xl"
  description="The Jinja2 template used to prompt the judge model."
/>
<FormElement
  inputType="textarea"
  id="system_prompt"
  label="System Prompt"
  bind:value={system_prompt}
  optional={true}
  height="base"
/>
