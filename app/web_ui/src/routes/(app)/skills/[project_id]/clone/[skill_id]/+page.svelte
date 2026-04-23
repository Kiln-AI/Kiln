<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import SkillForm from "../../../skill_form.svelte"
  import { page } from "$app/stores"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: skill_id = $page.params.skill_id!
  $: agentInfo.set({
    name: "Clone Skill",
    description: `Clone skill ID ${skill_id} in project ID ${project_id}. Create a new skill using an existing skill as a template.`,
  })
</script>

<div class="max-w-2xl">
  <AppPage
    title="Clone Skill"
    subtitle="Create a new skill, using an existing skill as a template"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/skills"
  >
    <SkillForm {project_id} {skill_id} clone_mode={true} />
  </AppPage>
</div>
