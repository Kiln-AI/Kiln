<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { current_task_prompts } from "$lib/stores"
  import type { PromptResponse } from "$lib/types"

  export let prompt_method: string

  export let exclude_cot = false
  export let custom_prompt_name: string | undefined = undefined
  export let description: string | undefined = undefined
  export let info_description: string | undefined = undefined
  $: options = build_prompt_options(
    $current_task_prompts,
    exclude_cot,
    custom_prompt_name,
  )

  function build_prompt_options(
    current_task_prompts: PromptResponse | null,
    exclude_cot: boolean,
    custom_prompt_name: string | undefined,
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
      static_prompts.push(["id::" + prompt.id, prompt.name])
    }
    if (static_prompts.length > 0) {
      grouped_options.push(["Saved Prompts", static_prompts])
    }
    return grouped_options
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
