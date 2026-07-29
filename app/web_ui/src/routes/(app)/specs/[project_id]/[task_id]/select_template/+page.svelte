<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import type { CarouselSectionItem } from "$lib/ui/kiln_section_types"
  import CarouselSection from "$lib/ui/carousel_section.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import { spec_categories } from "./spec_templates"
  import type { SpecTemplateData } from "./spec_templates"
  import { next_page_after_template, parseSpecWorkflow } from "../spec_utils"
  import { agentInfo } from "$lib/agent"

  // ### Spec Template Select ###

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: workflow = parseSpecWorkflow($page.url.searchParams.get("workflow"))
  $: agentInfo.set({
    name: "Select Eval Template",
    description: `Select an eval template as part of the eval creation process for project ID ${project_id}, task ID ${task_id}. Choose from available eval workflow templates.`,
  })

  function on_select(template_data: SpecTemplateData): () => void {
    return () => {
      goto(
        next_page_after_template(
          project_id,
          task_id,
          template_data.spec_type,
          workflow,
        ),
      )
    }
  }

  $: spec_sections = spec_categories.map((category) => ({
    category: category.category,
    items: category.templates.map(
      (template_data): CarouselSectionItem => ({
        type: "spec_template",
        name: formatSpecTypeName(template_data.spec_type),
        description: template_data.description,
        on_select: on_select(template_data),
      }),
    ),
  }))
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Select an Eval Template"
    subtitle="Select a template for what you want this task to enforce or avoid."
    breadcrumbs={[
      {
        label: "Evals",
        href: `/specs/${project_id}/${task_id}`,
      },
    ]}
  >
    <div class="space-y-8">
      {#each spec_sections as section}
        <CarouselSection title={section.category} items={section.items} />
      {/each}
    </div>
  </AppPage>
</div>
