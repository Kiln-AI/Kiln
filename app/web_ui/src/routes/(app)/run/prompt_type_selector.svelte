<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { current_task_prompts } from "$lib/stores"
  import type { PromptResponse } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"

  export let prompt_method: string
  export let linked_model_selection: string | undefined = undefined

  export let exclude_cot = false
  export let custom_prompt_name: string | undefined = undefined
  export let fine_tune_prompt_id: string | undefined = undefined
  export let description: string | undefined = undefined
  export let info_description: string | undefined = undefined
  $: options = build_prompt_options(
    $current_task_prompts,
    exclude_cot,
    custom_prompt_name,
    fine_tune_prompt_id,
  )

  function build_prompt_options(
    current_task_prompts: PromptResponse | null,
    exclude_cot: boolean,
    custom_prompt_name: string | undefined,
    fine_tune_prompt_id: string | undefined,
  ): [string, [unknown, string][]][] {
    if (!current_task_prompts) {
      return [["Loading...", []]]
    }

    const grouped_options: [string, [unknown, string][]][] = []

    const generators: [string, string][] = []
    for (const generator of current_task_prompts.generators) {
      if (generator.chain_of_thought && exclude_cot) {
        continue
      }
      generators.push([generator.id, generator.name])
    }
    if (generators.length > 0) {
      grouped_options.push(["Prompt Generators", generators])
    }

    if (fine_tune_prompt_id) {
      grouped_options.push([
        "Fine-Tune Prompt",
        [[fine_tune_prompt_id, "Fine-Tune Specific Prompt"]],
      ])
    }

    if (custom_prompt_name) {
      grouped_options.push(["Custom Prompt", [["custom", custom_prompt_name]]])
    }

    const static_prompts: [string, string][] = []
    for (const prompt of current_task_prompts.prompts) {
      if (!prompt.id) {
        continue
      }
      if (prompt.chain_of_thought_instructions && exclude_cot) {
        continue
      }
      static_prompts.push([prompt.id, prompt.name])
    }
    if (static_prompts.length > 0) {
      grouped_options.push(["Saved Prompts", static_prompts])
    }
    return grouped_options
  }

  // Finetunes are tuned with specific prompts.
  $: is_fine_tune_model =
    linked_model_selection &&
    linked_model_selection.startsWith("kiln_fine_tune/")
  $: {
    update_fine_tune_prompt_selection(linked_model_selection)
  }
  function update_fine_tune_prompt_selection(model_id: string | undefined) {
    if (model_id && model_id.startsWith("kiln_fine_tune/")) {
      // Select the fine-tune prompt automatically, when selecting a fine-tuned model
      const fine_tune_id = model_id.substring("kiln_fine_tune/".length)
      fine_tune_prompt_id = "fine_tune_prompt::" + fine_tune_id
      prompt_method = fine_tune_prompt_id
    } else {
      fine_tune_prompt_id = undefined
      if (prompt_method.startsWith("fine_tune_prompt::")) {
        // Reset to basic, since fine-tune prompt is no longer available
        prompt_method = "simple_prompt_builder"
      }
    }
    // This shouldn't be needed, but it is. Svelte doesn't re-evaluate the options when the fine-tune prompt id changes.
    options = build_prompt_options(
      $current_task_prompts,
      exclude_cot,
      custom_prompt_name,
      fine_tune_prompt_id,
    )
  }
</script>

<FormElement
  label="Prompt Method"
  inputType="select"
  {description}
  {info_description}
  bind:value={prompt_method}
  id="prompt_method"
  bind:select_options_grouped={options}
/>
{#if is_fine_tune_model && prompt_method != fine_tune_prompt_id}
  <Warning
    warning_message="We strongly recommend using prompt the model was trained on when running a fine-tuned model."
  />
{/if}
