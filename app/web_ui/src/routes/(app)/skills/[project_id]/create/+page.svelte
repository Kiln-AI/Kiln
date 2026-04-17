<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import SkillForm from "../../skill_form.svelte"
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: agentInfo.set({
    name: "Create Skill",
    description: `Create a new skill for project ID ${project_id}. Add reusable instructions for agents.`,
  })
</script>

<div class="max-w-2xl">
  <AppPage
    title="Add Skill"
    subtitle="Add reusable instructions for your agents, loaded into context only when needed."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/skills"
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${$ui_state.current_task_id}`,
      },
      {
        label: "Skills",
        href: `/skills/${project_id}`,
      },
    ]}
  >
    <SkillForm {project_id} />
  </AppPage>
</div>
