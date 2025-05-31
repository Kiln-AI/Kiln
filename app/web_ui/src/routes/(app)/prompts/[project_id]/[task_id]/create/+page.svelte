<script lang="ts">
  import { _ } from "svelte-i18n"
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
  let chain_of_thought_instructions = ""
  $: if (is_chain_of_thought && !chain_of_thought_instructions) {
    chain_of_thought_instructions = $_("prompts.chain_of_thought_default")
  }
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
  <AppPage
    title={$_("prompts.create_prompt")}
    subtitle={$_("prompts.create_prompt_subtitle", { values: { task_name } })}
  >
    <div class="max-w-[800px]">
      <FormContainer
        submit_label={$_("prompts.create_prompt_button")}
        on:submit={create_prompt}
        bind:error={create_error}
        bind:submitting={create_loading}
      >
        <FormElement
          label={$_("prompts.prompt_name")}
          id="prompt_name"
          bind:value={prompt_name}
          description={$_("prompts.prompt_name_description")}
          max_length={60}
        />

        <FormElement
          label={$_("prompts.prompt_description")}
          id="prompt_description"
          optional={true}
          bind:value={prompt_description}
          description={$_("prompts.prompt_description_description")}
        />

        <FormElement
          label={$_("prompts.prompt_label")}
          id="prompt"
          bind:value={prompt}
          inputType="textarea"
          tall={true}
          description={$_("prompts.prompt_input_description")}
          info_description={$_("prompts.prompt_info_description")}
        />
        <FormElement
          label={$_("prompts.chain_of_thought")}
          id="is_chain_of_thought"
          bind:value={is_chain_of_thought}
          description={$_("prompts.chain_of_thought_description")}
          inputType="select"
          select_options={[
            [false, $_("prompts.chain_of_thought_disabled")],
            [true, $_("prompts.chain_of_thought_enabled")],
          ]}
        />
        {#if is_chain_of_thought}
          <FormElement
            label={$_("prompts.chain_of_thought_instructions")}
            id="chain_of_thought_instructions"
            bind:value={chain_of_thought_instructions}
            inputType="textarea"
            description={$_(
              "prompts.chain_of_thought_instructions_description",
            )}
          />
        {/if}
      </FormContainer>
    </div>
  </AppPage>
</div>
