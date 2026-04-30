<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import GuideSetupForm, {
    type GuideSample,
    type GuideRule,
  } from "./guide_setup_form.svelte"
  import GuideRefineView from "./guide_refine_view.svelte"
  import GuidePreview from "./guide_preview.svelte"
  import DataGenDescription from "../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../synth_data_guidance_datamodel"
  import { onDestroy } from "svelte"
  import type { KilnAgentRunConfigProperties, Task } from "$lib/types"
  import { agentInfo } from "$lib/agent"
  import { current_task } from "$lib/stores"
  import AnalyzingAnimation from "$lib/ui/animations/analyzing_animation.svelte"
  import RefiningAnimation from "$lib/ui/animations/refining_animation.svelte"

  type GuideBuilderState =
    | "loading"
    | "setup"
    | "refine_existing"
    | "generating"
    | "preview"
    | "refining"

  // Start in "loading" so we can decide between setup vs refine-existing once
  // we know whether a guide is already saved. Without this we'd briefly flash
  // the setup form before the GET resolves.
  let current_state: GuideBuilderState = "loading"
  // Tracks which entry view to fall back to when an async step (preview/refine)
  // errors out, so refine-existing users don't get bounced into the setup form.
  let entry_state: "setup" | "refine_existing" = "setup"
  let error: KilnError | null = null
  let submitting = false

  // The single guide prompt string — the source of truth
  let guide: string = ""

  type PreviewSample = { input: string; output: string }
  let preview_samples: PreviewSample[] = []

  // Captured from the setup form so refine/regenerate can reuse them
  let captured_input_run_config: KilnAgentRunConfigProperties | null = null
  let captured_output_run_config: KilnAgentRunConfigProperties | null = null

  // The task being edited. Needed by the output run config dialog so it can
  // mirror the SDG output flow (prompt + tools/skills selectors at top level).
  let task: Task | null = null

  // Lifted out of GuideSetupForm so the user's examples/rules survive the
  // setup → generating → setup unmount cycle that happens when a preview
  // request fails. Without this, hitting an error wipes everything they
  // entered.
  let guide_examples: GuideSample[] = []
  let guide_rules: GuideRule[] = []

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Set Up Data Guide",
    description: `Setup the task data guide for project ${project_id}, task ${task_id}. The data guide describes the structure, rules, and examples for synthetic data generation.`,
  })

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

    // Load the task so the output run config dialog can pass current_task and
    // honor task.output_json_schema for structured output requirements.
    if ($current_task?.id === task_id) {
      task = $current_task
    } else {
      try {
        const { data: task_data } = await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}",
          { params: { path: { project_id, task_id } } },
        )
        if (task_data) {
          task = task_data
        }
      } catch {
        // Non-critical — output dialog will fall back to its defaults
      }
    }

    // If a saved guide already exists, skip the build-from-examples setup form
    // and drop the user into the refine flow. Otherwise start fresh.
    entry_state = guide.trim() ? "refine_existing" : "setup"
    current_state = entry_state
  })

  async function handle_generate_preview(
    event: CustomEvent<{
      guide: string
      input_run_config: KilnAgentRunConfigProperties
      output_run_config: KilnAgentRunConfigProperties
    }>,
  ) {
    error = null
    submitting = true
    current_state = "generating"

    try {
      captured_input_run_config = event.detail.input_run_config
      captured_output_run_config = event.detail.output_run_config
      guide = event.detail.guide

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            guide,
            run_config_properties: captured_input_run_config,
            output_run_config_properties: captured_output_run_config,
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
      current_state = entry_state
    } finally {
      submitting = false
    }
  }

  async function handle_refine(
    event: CustomEvent<{
      feedback: string
      rated_samples: { input: string; output: string; looks_good: boolean }[]
    }>,
  ) {
    error = null
    submitting = true
    current_state = "refining"

    try {
      if (!captured_input_run_config || !captured_output_run_config) {
        throw new KilnError("No model configuration available", null)
      }

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_refine",
        {
          params: { path: { project_id, task_id } },
          body: {
            current_guide: guide,
            feedback: event.detail.feedback,
            preview_samples: event.detail.rated_samples,
            run_config_properties: captured_input_run_config,
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
            run_config_properties: captured_input_run_config,
            output_run_config_properties: captured_output_run_config,
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
    // Stay in the "preview" state during the save — the PUT is essentially
    // instantaneous, so the FormContainer's bind:submitting spinner on the
    // Save Data Guide button is enough feedback. No need for a full-page
    // saving spinner.
    error = null
    submitting = true

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
    } finally {
      submitting = false
    }
  }

  function handle_save_with_guide(event: CustomEvent<{ guide: string }>) {
    guide = event.detail.guide
    return handle_save()
  }

  async function handle_regenerate() {
    if (!captured_input_run_config || !captured_output_run_config) return
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
            run_config_properties: captured_input_run_config,
            output_run_config_properties: captured_output_run_config,
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
    title={entry_state === "refine_existing"
      ? "Refine Data Guide"
      : "Set Up Data Guide"}
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

    {#if current_state === "loading"}
      <div class="flex flex-col items-center justify-center py-24 gap-4">
        <span class="loading loading-spinner loading-lg text-primary" />
      </div>
    {:else if current_state === "setup"}
      <GuideSetupForm
        {project_id}
        {task_id}
        {task}
        bind:guide_examples
        bind:guide_rules
        bind:page_error={error}
        on:generate_preview={handle_generate_preview}
      />
    {:else if current_state === "refine_existing"}
      <GuideRefineView
        {project_id}
        {guide}
        {task}
        bind:page_error={error}
        on:generate_preview={handle_generate_preview}
        on:save={handle_save_with_guide}
      />
    {:else if current_state === "generating"}
      <AnalyzingAnimation
        title="Generating Examples"
        description="Kiln is generating synthetic examples using your data guide so you can review them. Hold tight!"
      />
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
      <RefiningAnimation
        title="Refining Data Guide"
        description="Kiln is refining your data guide with the feedback you provided and generating fresh examples to review. Hold tight!"
      />
    {/if}
  </AppPage>
</div>
