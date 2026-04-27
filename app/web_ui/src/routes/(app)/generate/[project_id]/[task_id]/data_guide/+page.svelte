<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import GuideSetupForm from "./guide_setup_form.svelte"
  import GuidePreview from "./guide_preview.svelte"
  import DataGenDescription from "../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../synth_data_guidance_datamodel"
  import { onDestroy } from "svelte"
  import type { KilnAgentRunConfigProperties } from "$lib/types"

  type GuideBuilderState =
    | "setup"
    | "generating"
    | "preview"
    | "refining"
    | "saving"

  let current_state: GuideBuilderState = "setup"
  let error: KilnError | null = null
  let submitting = false

  // The single guide prompt string — the source of truth
  let guide: string = ""

  type PreviewSample = { input: string; output: string }
  let preview_samples: PreviewSample[] = []

  // Captured from the generate modal event, reused for refine
  let captured_run_config: KilnAgentRunConfigProperties | null = null

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  onMount(async () => {
    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        { params: { path: { project_id, task_id } } },
      )
      if (data) {
        guide = data.guide
      }
    } catch {
      // No existing guide
    }
  })

  async function handle_generate_preview(
    event: CustomEvent<{
      guide: string
      run_config: KilnAgentRunConfigProperties
    }>,
  ) {
    error = null
    submitting = true
    current_state = "generating"

    try {
      const run_config = event.detail.run_config
      captured_run_config = run_config
      guide = event.detail.guide

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            guide,
            run_config_properties: run_config,
            num_samples: 5,
          },
        },
      )

      if (api_error) throw api_error
      if (!data) throw new KilnError("No preview samples returned", null)

      preview_samples = data as PreviewSample[]
      current_state = "preview"
    } catch (e) {
      error = createKilnError(e)
      current_state = "setup"
    } finally {
      submitting = false
    }
  }

  async function handle_refine(event: CustomEvent<{ feedback: string }>) {
    error = null
    submitting = true
    current_state = "refining"

    try {
      if (!captured_run_config) {
        throw new KilnError("No model configuration available", null)
      }
      const run_config = captured_run_config

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_refine",
        {
          params: { path: { project_id, task_id } },
          body: {
            current_guide: guide,
            feedback: event.detail.feedback,
            preview_samples,
            run_config_properties: run_config,
          },
        },
      )

      if (api_error) throw api_error
      if (!data) throw new KilnError("No refinement returned", null)

      guide = data.refined_guide

      const { data: preview_data, error: preview_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            guide,
            run_config_properties: run_config,
            num_samples: 5,
          },
        },
      )

      if (preview_error) throw preview_error
      if (!preview_data)
        throw new KilnError("No preview samples returned", null)

      preview_samples = preview_data as PreviewSample[]
      current_state = "preview"
    } catch (e) {
      error = createKilnError(e)
      current_state = "preview"
    } finally {
      submitting = false
    }
  }

  async function handle_save() {
    error = null
    submitting = true
    current_state = "saving"

    try {
      const { error: api_error } = await client.PUT(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        {
          params: { path: { project_id, task_id } },
          body: {
            guide,
          },
        },
      )

      if (api_error) throw api_error

      goto(`/generate/${project_id}/${task_id}/synth?session_continued=true`)
    } catch (e) {
      error = createKilnError(e)
      current_state = "setup"
    } finally {
      submitting = false
    }
  }

  async function handle_regenerate() {
    if (!captured_run_config) return
    error = null
    submitting = true
    current_state = "generating"

    try {
      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            guide,
            run_config_properties: captured_run_config,
            num_samples: 5,
          },
        },
      )

      if (api_error) throw api_error
      if (!data) throw new KilnError("No preview samples returned", null)

      preview_samples = data as PreviewSample[]
      current_state = "preview"
    } catch (e) {
      error = createKilnError(e)
      current_state = "preview"
    } finally {
      submitting = false
    }
  }
</script>

<!-- TODO: Update read the docs link to point to new data guide docs -->
<div class="max-w-[1400px]">
  <AppPage
    title="Create Data Guide"
    subtitle="Help us understand what your data looks like so we can generate high-quality synthetic data."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    breadcrumbs={[
      {
        label: "Synthetic Data Generation",
        href: `/generate/${project_id}/${task_id}/synth`,
      },
    ]}
  >
    <DataGenDescription bind:guidance_data />

    {#if current_state === "setup"}
      <GuideSetupForm
        bind:error
        {project_id}
        {task_id}
        on:generate_preview={handle_generate_preview}
      />
    {:else if current_state === "generating"}
      <div class="flex flex-col items-center justify-center py-24 gap-4">
        <span class="loading loading-spinner loading-lg text-primary" />
        <div class="text-gray-500">Generating synthetic examples...</div>
      </div>
    {:else if current_state === "preview"}
      <GuidePreview
        {preview_samples}
        bind:guide
        bind:error
        bind:submitting
        on:refine={handle_refine}
        on:save={handle_save}
        on:regenerate={handle_regenerate}
      />
    {:else if current_state === "refining"}
      <div class="flex flex-col items-center justify-center py-24 gap-4">
        <span class="loading loading-spinner loading-lg text-primary" />
        <div class="text-gray-500">Refining and regenerating...</div>
      </div>
    {:else if current_state === "saving"}
      <div class="flex flex-col items-center justify-center py-24 gap-4">
        <span class="loading loading-spinner loading-lg text-primary" />
        <div class="text-gray-500">Saving guide...</div>
      </div>
    {/if}
  </AppPage>
</div>
