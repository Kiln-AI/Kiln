<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import type { CarouselSectionItem } from "$lib/ui/kiln_section_types"
  import CarouselSection from "$lib/ui/carousel_section.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import { spec_categories } from "./spec_templates"
  import Dialog from "$lib/ui/dialog.svelte"
  import ToolsSelector from "$lib/ui/run_config_component/tools_selector.svelte"
  import type { SpecTemplateData } from "./spec_templates"
  import { tool_id_to_function_name } from "$lib/stores/tools_store"

  // ### Spec Template Select ###

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  let current_params = new URLSearchParams()

  let current_template_data: SpecTemplateData | undefined = undefined

  function on_select(template_data: SpecTemplateData): () => void {
    return () => {
      current_template_data = template_data
      if (template_data.spec_type === "appropriate_tool_use") {
        tool_selection_dialog?.show()
      } else {
        go_to_create_spec(current_template_data)
      }
    }
  }

  async function go_to_create_spec(template_data: SpecTemplateData) {
    current_params = new URLSearchParams()
    current_params.set("type", template_data.spec_type)
    if (template_data.spec_type === "appropriate_tool_use" && selected_tool) {
      const tool_function_name = await tool_id_to_function_name(
        selected_tool,
        project_id,
        task_id,
      )
      current_params.set("tool_function_name", tool_function_name)
      current_params.set("tool_id", selected_tool)
    }
    goto(
      `/specs/${project_id}/${task_id}/spec_builder?${current_params.toString()}`,
    )
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

  let tool_selection_dialog: Dialog | undefined = undefined
  let selected_tool: string | null = null
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Select a Spec Template"
    subtitle="Select a template for what you want this task to enforce or avoid."
    breadcrumbs={[
      {
        label: "Specs & Evals",
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

  <Dialog
    bind:this={tool_selection_dialog}
    title="Tool for this Spec"
    action_buttons={[
      {
        label: "Next",
        isPrimary: true,
        asyncAction: async () => {
          if (!current_template_data) {
            return false
          }
          await go_to_create_spec(current_template_data)
          return true
        },
      },
    ]}
    on:close={() => {
      current_template_data = undefined
      selected_tool = null
    }}
  >
    <ToolsSelector
      {project_id}
      {task_id}
      label="Tool to Use"
      settings={{
        description: "Select the tool you want to use for this spec.",
        hide_info_description: true,
        single_select: true,
        optional: false,
      }}
      bind:single_select_selected_tool={selected_tool}
    />
  </Dialog>
</div>
