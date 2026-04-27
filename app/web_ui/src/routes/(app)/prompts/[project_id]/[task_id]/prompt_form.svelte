<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import {
    filename_string_validator_default,
    normalize_filename_string,
  } from "$lib/utils/input_validators"
  import { load_available_prompts } from "$lib/stores"
  import { goto } from "$app/navigation"
  import posthog from "posthog-js"

  export let project_id: string
  export let task_id: string
  export let clone_mode: boolean = false
  export let generator_id: string | null = null
  export let show_chain_of_thought: boolean = true
  export let initial_prompt_name: string = ""
  export let initial_prompt: string = ""
  export let initial_chain_of_thought_instructions: string | null = null
  export let redirect_from: string | null = null

  let prompt_name = initial_prompt_name
  let prompt = initial_prompt
  // Generator-backed prompts with thinking instructions always use CoT —
  // hide the toggle and show an editable CoT field instead.
  $: has_generator_cot =
    !show_chain_of_thought && !!initial_chain_of_thought_instructions
  let is_chain_of_thought = !!initial_chain_of_thought_instructions
  let chain_of_thought_instructions =
    initial_chain_of_thought_instructions ||
    "Think step by step, explaining your reasoning."
  let error: KilnError | null = null
  let submitting = false
  let complete = false

  $: cot_field_visible =
    (show_chain_of_thought && is_chain_of_thought) || has_generator_cot
  $: cot_enabled_for_submit =
    (show_chain_of_thought && is_chain_of_thought) || has_generator_cot

  async function handleSubmit() {
    try {
      submitting = true
      error = null
      prompt_name = normalize_filename_string(prompt_name)
      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/prompts",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
          body: {
            generator_id: generator_id,
            name: prompt_name,
            prompt: prompt,
            chain_of_thought_instructions: cot_enabled_for_submit
              ? chain_of_thought_instructions
              : null,
          },
        },
      )
      if (api_error) {
        throw api_error
      }
      if (!data || !data.id) {
        throw new Error("Invalid response from server")
      }
      posthog.capture("create_prompt", {
        is_chain_of_thought: is_chain_of_thought,
        from_generator: generator_id,
        is_clone: clone_mode,
      })

      await load_available_prompts(true)

      complete = true
      if (redirect_from === "optimize") {
        goto(
          `/optimize/${project_id}/${task_id}/run_config/create?prompt_id=${encodeURIComponent(`id::${data.id}`)}`,
        )
      } else {
        goto(`/prompts/${project_id}/${task_id}/saved/id::${data.id}`)
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }

  $: submit_label = clone_mode ? "Clone Prompt" : "Create Prompt"

  $: warn_before_unload =
    !complete &&
    (prompt !== initial_prompt ||
      prompt_name !== initial_prompt_name ||
      (cot_field_visible &&
        chain_of_thought_instructions !==
          (initial_chain_of_thought_instructions ||
            "Think step by step, explaining your reasoning.")) ||
      (show_chain_of_thought &&
        is_chain_of_thought !== !!initial_chain_of_thought_instructions))
</script>

<div class="max-w-[800px]">
  <FormContainer
    {submit_label}
    on:submit={handleSubmit}
    bind:error
    bind:submitting
    {warn_before_unload}
  >
    <FormElement
      label="Prompt Name"
      id="prompt_name"
      bind:value={prompt_name}
      description="A name to identify this prompt."
      max_length={120}
      validator={filename_string_validator_default}
    />

    <FormElement
      label="Prompt"
      id="prompt"
      bind:value={prompt}
      inputType="textarea"
      height="large"
      description="A prompt to use for this task."
      info_description="Model prompt such as 'You are a helpful assistant.'. This prompt is specific to this task. To use this prompt after creation, select it from the prompts dropdown."
    />
    {#if show_chain_of_thought}
      <FormElement
        label="Chain of Thought"
        id="is_chain_of_thought"
        bind:value={is_chain_of_thought}
        description="Should this prompt use chain of thought?"
        inputType="select"
        select_options={[
          [false, "Disabled"],
          [true, "Enabled"],
        ]}
      />
    {/if}
    {#if cot_field_visible}
      <FormElement
        label="Chain of Thought Instructions"
        id="chain_of_thought_instructions"
        bind:value={chain_of_thought_instructions}
        inputType="textarea"
        description="Instructions for the model's 'thinking' prior to answering. Required for chain of thought prompting."
      />
    {/if}
  </FormContainer>
</div>
