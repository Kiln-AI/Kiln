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

  function get_disabled_state(template: PromptGeneratorTemplate): {
    disabled: boolean
    reason?: string
  } {
    if (template.generator_id === "kiln_prompt_optimizer") {
      return { disabled: true, reason: "Coming soon" }
    }
    if (template.requires_repairs && !has_repair_data) {
      return {
        disabled: true,
        reason: "Requires repaired data in your dataset",
      }
    }
    if (template.requires_data && !has_rated_data) {
      return {
        disabled: true,
        reason: "Requires rated data in your dataset",
      }
    }
    return { disabled: false }
  }

  $: generator_sections = prompt_generator_categories.map((category) => ({
    category: category.category,
    items: category.templates.map(
      (template: PromptGeneratorTemplate): CarouselSectionItem => {
        const state = get_disabled_state(template)
        return {
          type: "prompt_generator" as const,
          name: template.name,
          description: template.description,
          on_select: on_select(template),
          disabled: state.disabled,
          disabled_reason: state.reason,
        }
      },
    ),
  }))
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create a Prompt"
    subtitle="Select a prompt generator to get started."
    breadcrumbs={[
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
          <CarouselSection title={section.category} items={section.items} />
        {/each}
      </div>
    {/if}
  </AppPage>
</div>
