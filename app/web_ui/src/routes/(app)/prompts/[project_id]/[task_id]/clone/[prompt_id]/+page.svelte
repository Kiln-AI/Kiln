<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"
  import { get_task_composite_id } from "$lib/stores"
  import { onMount } from "svelte"
  import PromptForm from "../../prompt_form.svelte"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: prompt_id = $page.params.prompt_id!
  $: agentInfo.set({
    name: "Clone Prompt",
    description: `Clone prompt ID ${prompt_id} for project ID ${project_id}, task ID ${task_id}.`,
  })

  let initial_prompt_name = ""
  let initial_prompt = ""
  let initial_chain_of_thought_instructions: string | null = null
  let loading = true
  let loading_error: KilnError | null = null

  onMount(async () => {
    try {
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

      initial_prompt_name = `Copy of ${source_prompt.name}`
      initial_prompt = source_prompt.prompt
      initial_chain_of_thought_instructions =
        source_prompt.chain_of_thought_instructions || null
    } catch (e) {
      loading_error = createKilnError(e)
    } finally {
      loading = false
    }
  })
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Clone Prompt"
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
        clone_mode={true}
        {initial_prompt_name}
        {initial_prompt}
        {initial_chain_of_thought_instructions}
      />
    {/if}
  </AppPage>
</div>
