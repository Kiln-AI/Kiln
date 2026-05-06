<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { load_task } from "$lib/stores"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { prompt_generator_categories } from "$lib/prompt_generators"
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

  $: generator_id = $page.url.searchParams.get("generator_id") || null
  let loading = true
  $: is_custom = !generator_id

  // Re-load when route params or generator search param changes
  let last_loaded_key: string | null = null
  $: if (project_id && task_id) {
    const key = `${project_id}/${task_id}/${generator_id ?? ""}`
    if (last_loaded_key !== key) {
      last_loaded_key = key
      loading_error = null
      initial_prompt = ""
      initial_chain_of_thought_instructions = null
      generator_name = ""
      initial_prompt_name = generate_memorable_name()
      load_create_prompt_data(project_id, task_id, generator_id)
    }
  }

  function is_stale(
    req_project_id: string,
    req_task_id: string,
    req_generator_id: string | null,
  ): boolean {
    return (
      req_project_id !== project_id ||
      req_task_id !== task_id ||
      req_generator_id !== generator_id
    )
  }

  async function load_create_prompt_data(
    req_project_id: string,
    req_task_id: string,
    req_generator_id: string | null,
  ) {
    try {
      loading = true

      if (req_generator_id) {
        const { data: prompt_response, error: get_error } = await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}/gen_prompt/{prompt_id}",
          {
            params: {
              path: {
                project_id: req_project_id,
                task_id: req_task_id,
                prompt_id: req_generator_id,
              },
            },
          },
        )
        if (is_stale(req_project_id, req_task_id, req_generator_id)) return
        if (get_error) {
          throw get_error
        }
        initial_prompt = prompt_response.prompt
        initial_chain_of_thought_instructions =
          prompt_response.chain_of_thought_instructions ?? null

        const template = prompt_generator_categories
          .flatMap((c) => c.templates)
          .find((t) => t.generator_id === req_generator_id)
        generator_name = template?.name || req_generator_id
        initial_prompt_name = `${generate_memorable_name()} - ${generator_name}`
      } else {
        generator_name = "Custom"

        const task = await load_task(req_project_id, req_task_id)
        if (is_stale(req_project_id, req_task_id, req_generator_id)) return
        if (task?.instruction) {
          initial_prompt = task.instruction
        }
      }
    } catch (e) {
      if (is_stale(req_project_id, req_task_id, req_generator_id)) return
      loading_error = createKilnError(e)
    } finally {
      if (!is_stale(req_project_id, req_task_id, req_generator_id)) {
        loading = false
      }
    }
  }
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
