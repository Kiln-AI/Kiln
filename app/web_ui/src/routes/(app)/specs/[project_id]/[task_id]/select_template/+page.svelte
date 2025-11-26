<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import type { CarouselSectionItem } from "$lib/ui/kiln_section_types"
  import type { SpecType } from "$lib/types"
  import CarouselSection from "$lib/ui/carousel_section.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import { spec_categories } from "./spec_templates"

  // ### Spec Template Select ###

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let current_params = new URLSearchParams()

  function get_on_select(spec_type: SpecType, template: string): () => void {
    return () => {
      current_params = new URLSearchParams({
        type: spec_type,
        template: template,
      })
      goto(
        `/specs/${project_id}/${task_id}/create_spec?${current_params.toString()}`,
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
        on_select: get_on_select(
          template_data.spec_type,
          template_data.template,
        ),
      }),
    ),
  }))
</script>

<AppPage
  title="Select a Spec Template"
  subtitle="Start by choosing the template that best fits the spec you want to create."
  breadcrumbs={[
    {
      label: "Specs",
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
