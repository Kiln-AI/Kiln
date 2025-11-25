<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import type { CarouselSectionItem } from "$lib/ui/kiln_section_types"
  import type { SpecType } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import CarouselSection from "$lib/ui/carousel_section.svelte"
  import AppPage from "../../../../../app_page.svelte"
  import { formatSpecTypeName } from "$lib/utils/formatters"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let not_implemented_dialog: Dialog | null = null
  let new_spec_dialog: Dialog | null = null

  function show_not_implemented() {
    not_implemented_dialog?.show()
  }

  type SpecTemplateData = {
    spec_type: SpecType
    description: string
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
        },
        {
          spec_type: "undesired_behaviour",
          description:
            "Build a spec to catch a specific issue you've encountered and prevent it from recurring.",
        },
        {
          spec_type: "tone",
          description: "Evaluate the tone and style of the model's output.",
        },
        {
          spec_type: "formatting",
          description:
            "Evaluate the formatting and structure of the model's output.",
        },
        {
          spec_type: "localization",
          description:
            "Evaluate the localization and language appropriateness of the model's output.",
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
        },
        {
          spec_type: "reference_answer_accuracy",
          description:
            "Evaluate model accuracy against ground-truth Q&A pairs.",
        },
        {
          spec_type: "intermediate_reasoning",
          description:
            "Evaluate the model's intermediate reasoning steps and thought process.",
        },
        {
          spec_type: "jailbreak",
          description:
            "Evaluate the user's ability to break out of the prompt, using tactics such as 'ignore previous instructions'.",
        },
        {
          spec_type: "prompt_leakage",
          description:
            "Evaluate the model's ability to prevent prompt leakage and system message exposure.",
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
        },
        {
          spec_type: "hallucinations",
          description:
            "Evaluate the model's output for hallucinations and fabricated information.",
        },
        {
          spec_type: "completeness",
          description:
            "Evaluate the completeness of the model's output and whether it addresses all aspects of the request.",
        },
        {
          spec_type: "consistency",
          description:
            "Evaluate the consistency of the model's output across different inputs and contexts.",
        },
      ],
    },
    {
      category: "Safety",
      templates: [
        {
          spec_type: "toxicity",
          description: "Evaluate the toxicity of the model's output.",
        },
        {
          spec_type: "bias",
          description:
            "Evaluate the model's output for gender bias, racial bias, and other bias.",
        },
        {
          spec_type: "maliciousness",
          description:
            "Evaluate the model's output for maliciousness including deception, exploitation, and harm.",
        },
        {
          spec_type: "nsfw",
          description:
            "Evaluate the model's output for not safe for work content.",
        },
        {
          spec_type: "taboo",
          description:
            "Evaluate the model's output for taboo or sensitive content.",
        },
      ],
    },
  ]

  const existing_spec_types: Set<SpecType> = new Set([
    "undesired_behaviour",
    "appropriate_tool_use",
    "reference_answer_accuracy",
    "factual_correctness",
    "toxicity",
    "bias",
    "maliciousness",
    "jailbreak",
  ])

  let current_params = new URLSearchParams()

  function get_on_select(
    spec_type: SpecType | null,
    template_description: string,
  ): () => void {
    if (!spec_type) {
      return show_not_implemented
    }
    if (existing_spec_types.has(spec_type)) {
      return () => {
        current_params = new URLSearchParams({
          type: spec_type,
          template_description: template_description,
        })
        // new_spec_dialog?.show()
        goto(
          `/specs/${project_id}/${task_id}/create_spec?${current_params.toString()}`,
        )
      }
    } else {
      return show_not_implemented
    }
  }

  $: spec_sections = spec_categories.map((category) => ({
    category: category.category,
    items: category.templates.map(
      (template): CarouselSectionItem => ({
        type: "spec_template",
        name: formatSpecTypeName(template.spec_type),
        description: template.description,
        on_select: get_on_select(template.spec_type, template.description),
      }),
    ),
  }))

  const use_carousel_for_spec_templates = true

  // let name = ""
  // let description = ""
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
  <div
    class={use_carousel_for_spec_templates ? "" : "max-w-4xl mt-12 space-y-12"}
  >
    <Dialog
      bind:this={not_implemented_dialog}
      title="Not Implemented Yet"
      action_buttons={[
        {
          label: "Close",
          action: () => true,
          isCancel: true,
        },
      ]}
    >
      <p>This feature is not yet implemented.</p>
    </Dialog>

    <div class="space-y-8">
      {#each spec_sections as section}
        <CarouselSection title={section.category} items={section.items} />
      {/each}
    </div>
  </div></AppPage
>

<!-- <Dialog bind:this={new_spec_dialog} title="New Spec">
  <FormContainer
    submit_label="Next"
    on:submit={() => {
      current_params.set("name", name)
      current_params.set("description", description)
      goto(
        `/specs/${project_id}/${task_id}/create_spec?${current_params.toString()}`,
      )
    }}
  >
    <FormElement
      label="Spec Name"
      description="A short name for your own reference."
      id="spec_name"
      bind:value={name}
    />
    <FormElement
      label="Spec Description"
      description="A short description for your own reference."
      id="spec_description"
      bind:value={description}
    />
  </FormContainer>
</Dialog> -->
