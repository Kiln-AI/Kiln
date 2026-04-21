<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { current_task } from "$lib/stores"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { prompt_generator_categories } from "../prompt_generators/prompt_generators"
  import { generate_memorable_name } from "$lib/utils/name_generator"
  import PromptForm from "../prompt_form.svelte"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Create Prompt",
    description: `Create a new prompt for project ID ${project_id}, task ID ${task_id}. Write or generate a custom prompt.`,
  })

  let generator_name = ""
  let initial_prompt_name = generate_memorable_name()
  let initial_prompt = ""
  let initial_chain_of_thought_instructions: string | null = null
  let loading_error: KilnError | null = null

  let generator_id: string | null = null
  let loading = true
  let is_custom = true

  onMount(async () => {
    generator_id = $page.url.searchParams.get("generator_id") || null
    is_custom = !generator_id

    if (generator_id) {
      try {
        const { data: prompt_response, error: get_error } = await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}/gen_prompt/{prompt_id}",
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
        initial_prompt = prompt_response.prompt
        initial_chain_of_thought_instructions =
          prompt_response.chain_of_thought_instructions ?? null

        const template = prompt_generator_categories
          .flatMap((c) => c.templates)
          .find((t) => t.generator_id === generator_id)
        generator_name = template?.name || generator_id
        initial_prompt_name = `${generate_memorable_name()} - ${generator_name}`
      } catch (e) {
        loading_error = createKilnError(e)
      }
    } else {
      generator_name = "Custom"

      if ($current_task?.instruction) {
        initial_prompt = $current_task.instruction
      }
    }

    loading = false
  })
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create Prompt"
    subtitle={generator_name}
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
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div class="text-error text-sm">
        {loading_error.getMessage() || "An unknown error occurred"}
      </div>
    {:else}
      <PromptForm
        {project_id}
        {task_id}
        {generator_id}
        show_chain_of_thought={is_custom}
        {initial_prompt_name}
        {initial_prompt}
        {initial_chain_of_thought_instructions}
        redirect_from={$page.url.searchParams.get("from")}
      />
    {/if}
  </AppPage>
</div>
