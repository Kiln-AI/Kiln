<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import type { CarouselSectionItem } from "$lib/ui/kiln_section_types"
  import CarouselSection from "$lib/ui/carousel_section.svelte"
  import AppPage from "../../../../app_page.svelte"
  import {
    prompt_generator_categories,
    type PromptGeneratorTemplate,
  } from "./prompt_generators"
  import { client } from "$lib/api_client"
  import { onMount } from "svelte"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  let has_rated_data = false
  let has_repair_data = false
  let loading = true
  let error: KilnError | null = null

  onMount(async () => {
    try {
      const { data, error: err } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/runs_summaries",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      if (err) {
        throw err
      }
      if (data) {
        has_rated_data = data.some(
          (run) =>
            run.rating &&
            run.rating.value !== null &&
            run.rating.value !== undefined,
        )
        has_repair_data = data.some((run) => run.repair_state === "repaired")
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  function on_select(template: PromptGeneratorTemplate): () => void {
    return () => {
      if (template.generator_id === "kiln_prompt_optimizer") {
        goto(
          `/prompt_optimization/${project_id}/${task_id}/create_prompt_optimization_job`,
        )
        return
      }

      const params = new URLSearchParams()
      const from = $page.url.searchParams.get("from")
      if (from) {
        params.set("from", from)
      }
      if (template.generator_id !== null) {
        params.set("generator_id", template.generator_id)
      }
      const qs = params.toString()
      goto(`/prompts/${project_id}/${task_id}/create${qs ? `?${qs}` : ""}`)
    }
  }

  function get_disabled_state(
    template: PromptGeneratorTemplate,
    has_rated: boolean,
    has_repair: boolean,
  ): {
    disabled: boolean
    reason?: string
    docs_link?: string
  } {
    if (template.requires_repairs && !has_repair) {
      return {
        disabled: true,
        reason:
          "This prompt generator uses repaired examples from your dataset to help the model learn from common errors. To use it, you'll need to repair at least one response in your dataset first.",
        docs_link: "https://docs.kiln.tech/docs/repairing-responses",
      }
    }
    if (template.requires_data && !has_rated) {
      return {
        disabled: true,
        reason:
          "This prompt generator uses rated examples from your dataset. To use it, you'll need to rate at least one response in your dataset first.",
        docs_link: "https://docs.kiln.tech/docs/reviewing-and-rating",
      }
    }
    return { disabled: false }
  }

  $: generator_sections = prompt_generator_categories.map((category) => ({
    category: category.category,
    items: category.templates.map(
      (template: PromptGeneratorTemplate): CarouselSectionItem => {
        const state = get_disabled_state(
          template,
          has_rated_data,
          has_repair_data,
        )
        return {
          type: "prompt_generator" as const,
          name: template.name,
          description: template.description,
          on_select: on_select(template),
          disabled: state.disabled,
          disabled_reason: state.reason,
          disabled_docs_link: state.docs_link,
          recommended: template.recommended,
        }
      },
    ),
  }))
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create Prompt"
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
    {:else if error}
      <div class="text-error text-sm">
        {error?.getMessage() || "An unknown error occurred"}
      </div>
    {:else}
      <div class="space-y-8">
        {#each generator_sections as section}
          <CarouselSection
            title={section.category}
            items={section.items}
            min_height={150}
            min_width={250}
          />
        {/each}
      </div>
    {/if}
  </AppPage>
</div>
