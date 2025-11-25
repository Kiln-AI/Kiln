<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import type { CarouselSectionItem } from "$lib/ui/kiln_section_types"
  import type { SpecType } from "$lib/types"
  import CarouselSection from "$lib/ui/carousel_section.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { formatSpecTypeName } from "$lib/utils/formatters"

  // ### Spec Template Select ###

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  type SpecTemplateData = {
    spec_type: SpecType
    description: string
    template: string
  }

  type SpecCategoryData = {
    category: string
    templates: SpecTemplateData[]
  }

  const spec_categories: SpecCategoryData[] = [
    {
      category: "Behavioral",
      templates: [
        {
          spec_type: "desired_behaviour",
          description:
            "Define a specific desired behaviour you want your task to follow.",
          template: "",
        },
        {
          spec_type: "undesired_behaviour",
          description:
            "Build a spec to catch a specific issue you've encountered and prevent it from recurring.",
          template: "",
        },
        {
          spec_type: "tone",
          description: "Evaluate the tone and style of the model's output.",
          template: "",
        },
        {
          spec_type: "formatting",
          description:
            "Evaluate the formatting and structure of the model's output.",
          template: "",
        },
        {
          spec_type: "localization",
          description:
            "Evaluate the localization and language appropriateness of the model's output.",
          template: "",
        },
      ],
    },
    {
      category: "Execution",
      templates: [
        {
          spec_type: "appropriate_tool_use",
          description:
            "Evaluate your model's ability to appropriately invoke a tool.",
          template: "",
        },
        {
          spec_type: "reference_answer_accuracy",
          description:
            "Evaluate model accuracy against ground-truth Q&A pairs.",
          template: "",
        },
        {
          spec_type: "intermediate_reasoning",
          description:
            "Evaluate the model's intermediate reasoning steps and thought process.",
          template: "",
        },
        {
          spec_type: "jailbreak",
          description:
            "Evaluate the user's ability to break out of the prompt, using tactics such as 'ignore previous instructions'.",
          template: "",
        },
        {
          spec_type: "prompt_leakage",
          description:
            "Evaluate the model's ability to prevent prompt leakage and system message exposure.",
          template: "",
        },
      ],
    },
    {
      category: "Quality",
      templates: [
        {
          spec_type: "factual_correctness",
          description:
            "Evaluate the model's output for factual correctness and critical omissions.",
          template: "",
        },
        {
          spec_type: "hallucinations",
          description:
            "Evaluate the model's output for hallucinations and fabricated information.",
          template: "",
        },
        {
          spec_type: "completeness",
          description:
            "Evaluate the completeness of the model's output and whether it addresses all aspects of the request.",
          template: "",
        },
        {
          spec_type: "consistency",
          description:
            "Evaluate the consistency of the model's output across different inputs and contexts.",
          template: "",
        },
      ],
    },
    {
      category: "Safety",
      templates: [
        {
          spec_type: "toxicity",
          description: "Evaluate the toxicity of the model's output.",
          template: "",
        },
        {
          spec_type: "bias",
          description:
            "Evaluate the model's output for gender bias, racial bias, and other bias.",
          template: "",
        },
        {
          spec_type: "maliciousness",
          description:
            "Evaluate the model's output for maliciousness including deception, exploitation, and harm.",
          template: "",
        },
        {
          spec_type: "nsfw",
          description:
            "Evaluate the model's output for not safe for work content.",
          template: "",
        },
        {
          spec_type: "taboo",
          description:
            "Evaluate the model's output for taboo or sensitive content.",
          template: "",
        },
      ],
    },
  ]

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
