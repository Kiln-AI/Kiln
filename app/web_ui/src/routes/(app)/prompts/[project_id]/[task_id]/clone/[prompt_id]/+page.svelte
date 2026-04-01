<script lang="ts">
  import AppPage from "../../../../../app_page.svelte"
  import { page } from "$app/stores"
  import PromptForm from "../../prompt_form.svelte"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: prompt_id = $page.params.prompt_id!
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
    <PromptForm {project_id} {task_id} clone_mode {prompt_id} />
  </AppPage>
</div>
