<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { current_task, load_available_prompts } from "$lib/stores"
  import { page } from "$app/stores"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import posthog from "posthog-js"
  import { onMount } from "svelte"
  import { prompt_generator_categories } from "../prompt_generators/prompt_generators"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  let generator_name = ""
  let prompt_name = ""
  let prompt = ""
  let is_chain_of_thought = false
  let chain_of_thought_instructions =
    "Think step by step, explaining your reasoning."
  let create_error: KilnError | null = null
  let create_loading = false
  let warn_before_unload = false

  let generator_id: string | null = null
  let loading_generator = false
  let is_custom = true

  let initial_prompt = ""
  let initial_loaded = false

  onMount(async () => {
    generator_id = $page.url.searchParams.get("generator_id") || null
    is_custom = !generator_id

    if (generator_id) {
      loading_generator = true
      try {
        const { data: prompt_response, error: get_error } = await client.GET(
          "/api/projects/{project_id}/task/{task_id}/gen_prompt/{prompt_id}",
          {
            params: {
              path: {
                project_id,
                task_id,
                prompt_id: generator_id,
              },
            },
          },
        )
        if (get_error) {
          throw get_error
        }
        prompt = prompt_response.prompt

        const template = prompt_generator_categories
          .flatMap((c) => c.templates)
          .find((t) => t.generator_id === generator_id)
        generator_name = template?.name || generator_id

        initial_prompt = prompt
      } catch (e) {
        create_error = createKilnError(e)
      } finally {
        loading_generator = false
      }
    } else {
      generator_name = "Custom"

      if ($current_task?.instruction) {
        prompt = $current_task.instruction
      }
      initial_prompt = prompt
    }

    initial_loaded = true
  })

  async function create_prompt() {
    try {
      create_loading = true
      create_error = null
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/task/{task_id}/prompt",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
          body: {
            name: prompt_name,
            prompt: prompt,
            chain_of_thought_instructions:
              is_custom && is_chain_of_thought
                ? chain_of_thought_instructions
                : null,
          },
        },
      )
      if (error) {
        throw error
      }
      if (!data || !data.id) {
        throw new Error("Invalid response from server")
      }
      posthog.capture("create_prompt", {
        is_chain_of_thought: is_chain_of_thought,
        from_generator: generator_id,
      })

      await load_available_prompts(true)

      warn_before_unload = false
      const from = $page.url.searchParams.get("from")
      if (from === "optimize") {
        goto(
          `/optimize/${project_id}/${task_id}/create_run_config?prompt_id=${encodeURIComponent(`id::${data.id}`)}`,
        )
      } else {
        goto(`/prompts/${project_id}/${task_id}/saved/id::${data.id}`)
      }
    } catch (e) {
      create_error = createKilnError(e)
    } finally {
      create_loading = false
    }
  }

  $: if (initial_loaded) {
    warn_before_unload =
      prompt !== initial_prompt ||
      !!prompt_name ||
      (is_custom && is_chain_of_thought)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create a Prompt"
    subtitle={`${generator_name}`}
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/prompts"
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${task_id}`,
      },
      {
        label: "Prompts",
        href: `/prompts/${project_id}/${task_id}`,
      },
      {
        label: "Prompt Generators",
        href: `/prompts/${project_id}/${task_id}/prompt_generators`,
      },
    ]}
  >
    {#if loading_generator}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else}
      <div class="max-w-[800px]">
        <FormContainer
          submit_label="Create Prompt"
          on:submit={create_prompt}
          bind:error={create_error}
          bind:submitting={create_loading}
          {warn_before_unload}
        >
          <FormElement
            label="Prompt Name"
            id="prompt_name"
            bind:value={prompt_name}
            description="A short name to uniquely identify this prompt."
            max_length={60}
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
          {#if is_custom}
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
  </AppPage>
</div>
