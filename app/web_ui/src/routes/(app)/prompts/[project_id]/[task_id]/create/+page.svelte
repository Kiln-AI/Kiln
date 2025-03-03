<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { current_task, load_available_prompts } from "$lib/stores"
  import { page } from "$app/stores"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: task_name = $current_task?.id == task_id ? $current_task?.name : "unknown"

  let prompt_name = ""
  let prompt_description = ""
  let prompt = ""
  let is_chain_of_thought = false
  let chain_of_thought_instructions =
    "Think step by step, explaining your reasoning."
  let create_error: KilnError | null = null
  let create_loading = false

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
            description: prompt_description,
            prompt: prompt,
            chain_of_thought_instructions: is_chain_of_thought
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

      // Success! Reload then navigate to the new prompt
      await load_available_prompts()
      goto(`/prompts/${project_id}/${task_id}/saved/id::${data.id}`)
    } catch (e) {
      create_error = createKilnError(e)
    } finally {
      create_loading = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage title="Create a Prompt" subtitle={`For the task "${task_name}"`}>
    <div class="max-w-[800px]">
      <FormContainer
        submit_label="Create Prompt"
        on:submit={create_prompt}
        bind:error={create_error}
        bind:submitting={create_loading}
      >
        <FormElement
          label="Prompt Name"
          id="prompt_name"
          bind:value={prompt_name}
          description="A short name to uniquely identify this prompt."
          max_length={60}
        />

        <FormElement
          label="Prompt Description"
          id="prompt_description"
          bind:value={prompt_description}
          description="A description of the prompt for your reference."
        />

        <FormElement
          label="Prompt"
          id="prompt"
          bind:value={prompt}
          inputType="textarea"
          tall={true}
          description="A prompt to use for this task."
          info_description="A LLM prompt such as 'You are a helpful assistant.'. This prompt is specific to this task. To use this prompt after creation, select it from the prompts dropdown."
        />
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
      </FormContainer>
    </div>
  </AppPage>
</div>
