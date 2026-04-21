<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import { current_task_prompts } from "$lib/stores"
  import type { PromptResponse } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"
  import type { OptionGroup, Option } from "$lib/ui/fancy_select_types"
  import { getStaticPromptDisplayName } from "$lib/utils/run_config_formatters"
  import { client } from "$lib/api_client"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { prompt_generator_categories } from "$lib/prompt_generators"

  export let prompt_method: string
  export let linked_model_selection: string | null | undefined = undefined

  export let exclude_cot = false
  export let custom_prompt_name: string | undefined = undefined
  export let fine_tune_prompt_id: string | undefined = undefined
  export let description: string | undefined = undefined
  export let info_description: string | undefined = undefined
  export let project_id: string | null = null
  export let task_id: string | null = null

  let has_rated_data = false
  let has_repair_data = false
  let data_requirements_checked = false

  $: generator_requirements = build_generator_requirements()

  function build_generator_requirements(): Record<
    string,
    { requires_data: boolean; requires_repairs: boolean }
  > {
    const map: Record<
      string,
      { requires_data: boolean; requires_repairs: boolean }
    > = {}
    for (const category of prompt_generator_categories) {
      for (const template of category.templates) {
        if (template.generator_id) {
          map[template.generator_id] = {
            requires_data: template.requires_data,
            requires_repairs: template.requires_repairs,
          }
        }
      }
    }
    return map
  }

  function generator_disabled_reason(generator_id: string): string | null {
    const req = generator_requirements[generator_id]
    if (!req || !data_requirements_checked) {
      return null
    }
    if (req.requires_repairs && !has_repair_data) {
      return "Requires at least one repaired response in your dataset."
    }
    if (req.requires_data && !has_rated_data) {
      return "Requires at least one rated response in your dataset."
    }
    return null
  }

  // Re-fetch rated/repair data whenever project_id or task_id changes so the
  // generator disabled states stay in sync if the parent swaps tasks.
  let requirements_loaded_key: string | null = null
  $: load_data_requirements(project_id, task_id)

  async function load_data_requirements(
    project_id: string | null,
    task_id: string | null,
  ) {
    if (!project_id || !task_id) {
      requirements_loaded_key = null
      data_requirements_checked = false
      has_rated_data = false
      has_repair_data = false
      return
    }
    const key = `${project_id}:${task_id}`
    if (requirements_loaded_key === key) return
    requirements_loaded_key = key
    data_requirements_checked = false
    has_rated_data = false
    has_repair_data = false
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/runs_summaries",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      // Drop stale responses if the task was swapped while the request was
      // in flight — avoids overwriting the new task's flags with old data.
      if (requirements_loaded_key !== key) return
      if (error) return
      if (data) {
        has_rated_data = data.some(
          (run) =>
            run.rating &&
            run.rating.value !== null &&
            run.rating.value !== undefined,
        )
        has_repair_data = data.some(
          (run) => run.repair_state?.toLowerCase() === "repaired",
        )
      }
    } finally {
      if (requirements_loaded_key === key) {
        data_requirements_checked = true
      }
    }
  }

  $: options = build_prompt_options(
    $current_task_prompts,
    exclude_cot,
    custom_prompt_name,
    fine_tune_prompt_id,
    project_id,
    task_id,
    data_requirements_checked,
    has_rated_data,
    has_repair_data,
  )

  function build_prompt_options(
    current_task_prompts: PromptResponse | null,
    exclude_cot: boolean,
    custom_prompt_name: string | undefined,
    fine_tune_prompt_id: string | undefined,
    project_id: string | null,
    task_id: string | null,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _requirements_checked: boolean,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _has_rated: boolean,
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    _has_repair: boolean,
  ): OptionGroup[] {
    if (!current_task_prompts) {
      return []
    }

    const grouped_options: OptionGroup[] = []

    const generators: Option[] = []
    for (const generator of current_task_prompts.generators) {
      if (generator.chain_of_thought && exclude_cot) {
        continue
      }
      const disabled_reason = generator_disabled_reason(generator.id)
      generators.push({
        value: generator.id,
        label: generator.name,
        description: disabled_reason ?? generator.short_description,
        disabled: !!disabled_reason,
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
      static_prompts.push({
        value: prompt.id,
        label: getStaticPromptDisplayName(
          prompt.name,
          prompt.generator_id,
          current_task_prompts,
        ),
      })
    }
    const saved_prompts_action =
      project_id && task_id
        ? {
            action_label: "Create New",
            action_handler: () => {
              const params = new URLSearchParams()
              const from = $page.url.searchParams.get("from")
              if (from) {
                params.set("from", from)
              }
              const qs = params.toString()
              goto(
                `/prompts/${project_id}/${task_id}/prompt_generators${
                  qs ? `?${qs}` : ""
                }`,
              )
            },
          }
        : {}
    if (static_prompts.length > 0) {
      grouped_options.push({
        label: "Saved Prompts",
        options: static_prompts,
        ...saved_prompts_action,
      })
    } else if (project_id && task_id) {
      grouped_options.push({
        label: "Saved Prompts",
        options: [],
        ...saved_prompts_action,
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
  function update_fine_tune_prompt_selection(
    model_id: string | null | undefined,
  ) {
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
      project_id,
      task_id,
      data_requirements_checked,
      has_rated_data,
      has_repair_data,
    )
  }
</script>

<FormElement
  label="Prompt Method"
  inputType="fancy_select"
  empty_state_message="Loading prompts..."
  empty_state_subtitle="Please wait."
  {description}
  {info_description}
  bind:value={prompt_method}
  id="prompt_method"
  bind:fancy_select_options={options}
/>

{#if is_fine_tune_model && prompt_method != fine_tune_prompt_id}
  <Warning
    warning_message="We strongly recommend using prompt the model was trained on when running a fine-tuned model."
  />
{/if}
