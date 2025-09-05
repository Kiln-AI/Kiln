<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { current_task_prompts } from "$lib/stores"
  import type { PromptResponse } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  export let prompt_method: string
  export let linked_model_selection: string | undefined = undefined

  export let exclude_cot = false
  export let custom_prompt_name: string | undefined = undefined
  export let fine_tune_prompt_id: string | undefined = undefined
  export let description: string | undefined = undefined
  export let info_description: string | undefined = undefined
  export let read_only: boolean = false

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
  ): OptionGroup[] {
    if (!current_task_prompts) {
      return [
        {
          label: "Loading...",
          options: [],
        },
      ]
    }

    const grouped_options: OptionGroup[] = []

    const generators: Option[] = []
    for (const generator of current_task_prompts.generators) {
      if (generator.chain_of_thought && exclude_cot) {
        continue
      }
      generators.push({
        value: generator.id,
        label: generator.name,
        description: generator.short_description,
      })
    }
    if (generators.length > 0) {
      grouped_options.push({
        label: "Prompt Generators",
        options: generators,
      })
    }

    if (fine_tune_prompt_id) {
      grouped_options.push({
        label: "Fine-Tune Prompt",
        options: [
          {
            value: fine_tune_prompt_id,
            label: "Fine-Tune Prompt",
            description: "The exact prompt used to fine-tune this model.",
            badge: "Recommended",
            badge_color: "primary",
          },
        ],
      })
    }

    if (custom_prompt_name) {
      grouped_options.push({
        label: "Custom Prompt",
        options: [{ value: "custom", label: custom_prompt_name }],
      })
    }

    const static_prompts: Option[] = []
    for (const prompt of current_task_prompts.prompts) {
      if (!prompt.id) {
        continue
      }
      if (prompt.chain_of_thought_instructions && exclude_cot) {
        continue
      }
      static_prompts.push({ value: prompt.id, label: prompt.name })
    }
    if (static_prompts.length > 0) {
      grouped_options.push({
        label: "Saved Prompts",
        options: static_prompts,
      })
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

  // Get display name for selected prompt method
  $: selected_prompt_name = get_selected_prompt_name(prompt_method, options)

  function get_selected_prompt_name(
    selected_value: string,
    option_groups: OptionGroup[],
  ): string {
    for (const group of option_groups) {
      for (const option of group.options) {
        if (option.value === selected_value) {
          return option.label
        }
      }
    }
    return selected_value
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

{#if read_only}
  <FormElement
    label="Prompt Method"
    inputType="header_only"
    {description}
    {info_description}
    id="prompt_method_readonly"
  />
  <div class="relative">
    <div
      class="select select-bordered w-full flex items-center bg-base-200/50 text-base-content/70"
      style="background-image: none;"
    >
      <span class="truncate">{selected_prompt_name}</span>
    </div>
  </div>
{:else}
  <FormElement
    label="Prompt Method"
    inputType="fancy_select"
    {description}
    {info_description}
    bind:value={prompt_method}
    id="prompt_method"
    bind:fancy_select_options={options}
  />
{/if}

{#if is_fine_tune_model && prompt_method != fine_tune_prompt_id}
  <Warning
    warning_message="We strongly recommend using prompt the model was trained on when running a fine-tuned model."
  />
{/if}
