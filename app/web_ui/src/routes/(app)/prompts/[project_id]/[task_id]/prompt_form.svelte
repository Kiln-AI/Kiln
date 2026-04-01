<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { load_available_prompts, get_task_composite_id } from "$lib/stores"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"
  import posthog from "posthog-js"

  export let project_id: string
  export let task_id: string
  export let clone_mode: boolean = false
  export let prompt_id: string | undefined = undefined
  export let generator_id: string | null = null
  export let show_chain_of_thought: boolean = true
  export let initial_prompt_name: string = ""
  export let initial_prompt: string = ""
  export let redirect_from: string | null = null

  let prompt_name = initial_prompt_name
  let prompt = initial_prompt
  let is_chain_of_thought = false
  let chain_of_thought_instructions =
    "Think step by step, explaining your reasoning."
  let error: KilnError | null = null
  let submitting = false
  let loading = false
  let loading_error: KilnError | null = null
  let complete = false

  onMount(async () => {
    if (clone_mode && prompt_id) {
      await load_prompt_for_clone()
    }
  })

  async function load_prompt_for_clone() {
    if (!prompt_id) {
      loading_error = new KilnError("Prompt ID is required for cloning.")
      return
    }
    try {
      loading = true
      loading_error = null
      await load_task_prompts(project_id, task_id)
      const task_prompts =
        $prompts_by_task_composite_id[
          get_task_composite_id(project_id, task_id)
        ]
      const source_prompt = task_prompts?.prompts.find(
        (p) => p.id === prompt_id,
      )

      if (!source_prompt) {
        throw new KilnError("Source prompt not found.")
      }

      prompt_name = `Copy of ${source_prompt.name}`
      prompt = source_prompt.prompt
      if (source_prompt.chain_of_thought_instructions) {
        is_chain_of_thought = true
        chain_of_thought_instructions =
          source_prompt.chain_of_thought_instructions
      }
    } catch (e) {
      loading_error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  async function handleSubmit() {
    try {
      submitting = true
      error = null
      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/task/{task_id}/prompt",
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
            chain_of_thought_instructions:
              show_chain_of_thought && is_chain_of_thought
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
      (show_chain_of_thought && is_chain_of_thought))
</script>

{#if clone_mode && loading}
  <div class="w-full min-h-[50vh] flex justify-center items-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else if clone_mode && loading_error}
  <div class="text-error text-sm">
    {loading_error.getMessage() || "An unknown error occurred"}
  </div>
{:else}
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
        {#if is_chain_of_thought}
          <FormElement
            label="Chain of Thought Instructions"
            id="chain_of_thought_instructions"
            bind:value={chain_of_thought_instructions}
            inputType="textarea"
            description="Instructions for the model's 'thinking' prior to answering. Required for chain of thought prompting."
          />
        {/if}
      {/if}
    </FormContainer>
  </div>
{/if}
