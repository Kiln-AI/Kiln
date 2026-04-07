<script lang="ts">
  import { page } from "$app/stores"
  import AppPage from "../../../../app_page.svelte"
  import { doc_skill_templates } from "../add_doc_skill/doc_skill_templates"
  import CreateDocSkillForm from "./create_doc_skill_form.svelte"
  import { ui_state } from "$lib/stores"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: agentInfo.set({
    name: "Create Doc Skill",
    description: `Create a new doc skill configuration for project ID ${project_id}.`,
  })
  const template_id = $page.url.searchParams.get("template_id")
  const template = template_id ? doc_skill_templates[template_id] : null
  const clone_id = $page.url.searchParams.get("clone")
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create Doc Skill"
    subtitle="Define parameters for how this skill will process your documents"
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${$ui_state.current_task_id}`,
      },
      {
        label: "Docs & Search",
        href: `/docs/${project_id}`,
      },
      {
        label: "Doc Skills",
        href: `/docs/doc_skills/${project_id}`,
      },
      {
        label: "Add Doc Skill",
        href: `/docs/doc_skills/${project_id}/add_doc_skill`,
      },
    ]}
  >
    <CreateDocSkillForm {template} {clone_id} />
  </AppPage>
</div>
