<script lang="ts">
  // Refine flow: previewing + iterating on a saved data guide. Reached from
  // /data_guide via a handoff store carrying the chosen run configs and the
  // (possibly edited) guide text. The saved-guide read-only view lives at
  // /data_guide; this page only handles the active refine loop.
  import AppPage from "../../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, onDestroy } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { get } from "svelte/store"
  import GuidePreview from "../../data_guide_setup/guide_preview.svelte"
  import DataGenDescription from "../../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../../synth_data_guidance_datamodel"
  import type { KilnAgentRunConfigProperties } from "$lib/types"
  import { agentInfo } from "$lib/agent"
  import AnalyzingAnimation from "$lib/ui/animations/analyzing_animation.svelte"
  import RefiningAnimation from "$lib/ui/animations/refining_animation.svelte"
  import { pending_data_guide_refine_handoff } from "../refine_handoff_store"

  type RefineState =
    | "loading"
    | "generating"
    | "preview"
    | "refining"
    | "regenerating"
    | "load_error"

  let current_state: RefineState = "loading"
  let error: KilnError | null = null
  let submitting = false
  // Flipped true once the guide is saved and we're navigating away. Suppresses
  // GuidePreview's unsaved-changes warn so the post-save goto doesn't prompt.
  let saved = false

  let examples_md: string = ""
  let rules_md: string = ""

  type PreviewSample = { input: string; output: string }
  type ReviewedSample = {
    input: string
    output: string
    looks_good: boolean | undefined
  }
  let preview_samples: PreviewSample[] = []
  let preview_initial_examples_md: string = ""
  let preview_initial_rules_md: string = ""
  let reviewed_samples: ReviewedSample[] = []
  let general_feedback: string = ""

  let captured_input_run_config: KilnAgentRunConfigProperties | null = null
  let captured_output_run_config: KilnAgentRunConfigProperties | null = null

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Refine Data Guide",
    description: `Refine the saved task data guide for project ${project_id}, task ${task_id}.`,
  })

  onMount(async () => {
    const handoff = get(pending_data_guide_refine_handoff)
    if (!handoff) {
      // No seed (direct URL hit / hard refresh) — the saved-guide view is
      // where this flow starts.
      goto(`/generate/${project_id}/${task_id}/data_guide`, {
        replaceState: true,
      })
      return
    }
    pending_data_guide_refine_handoff.set(null)

    examples_md = handoff.examples_md
    rules_md = handoff.rules_md
    captured_input_run_config = handoff.input_run_config
    captured_output_run_config = handoff.output_run_config

    await run_initial_preview()
  })

  async function run_initial_preview() {
    error = null
    submitting = true
    current_state = "generating"

    try {
      if (!captured_input_run_config || !captured_output_run_config) {
        throw new KilnError("No model configuration available", null)
      }

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            examples_md,
            rules_md,
            run_config_properties: captured_input_run_config,
            output_run_config_properties: captured_output_run_config,
            num_samples: 5,
          },
        },
      )

      if (api_error) throw api_error
      if (!data) throw new KilnError("No preview samples returned", null)

      preview_samples = data as PreviewSample[]
      reviewed_samples = preview_samples.map((s) => ({
        input: s.input,
        output: s.output,
        looks_good: undefined,
      }))
      general_feedback = ""
      preview_initial_examples_md = examples_md
      preview_initial_rules_md = rules_md
      current_state = "preview"
    } catch (e) {
      // Surface the failure on this page rather than silently bouncing back
      // to /data_guide, which would lose the error and leave the user with
      // no idea why the refine flow didn't start.
      error = createKilnError(e)
      current_state = "load_error"
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

    const has_negative_feedback =
      event.detail.rated_samples.some((s) => !s.looks_good) ||
      event.detail.feedback.trim().length > 0

    current_state = has_negative_feedback ? "refining" : "regenerating"

    try {
      if (!captured_input_run_config || !captured_output_run_config) {
        throw new KilnError("No model configuration available", null)
      }

      if (has_negative_feedback) {
        const { data, error: api_error } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_refine",
          {
            params: { path: { project_id, task_id } },
            body: {
              current_examples_md: examples_md,
              current_rules_md: rules_md,
              feedback: event.detail.feedback,
              preview_samples: event.detail.rated_samples,
              run_config_properties: captured_input_run_config,
            },
          },
        )

        if (api_error) throw api_error
        if (!data) throw new KilnError("No refinement returned", null)

        rules_md = data.refined_rules_md
      }

      const { data: preview_data, error: preview_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            examples_md,
            rules_md,
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
      reviewed_samples = preview_samples.map((s) => ({
        input: s.input,
        output: s.output,
        looks_good: undefined,
      }))
      general_feedback = ""
      preview_initial_examples_md = examples_md
      preview_initial_rules_md = rules_md
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

    try {
      const { error: api_error } = await client.PUT(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        {
          params: { path: { project_id, task_id } },
          body: { examples_md, rules_md },
        },
      )

      if (api_error) throw api_error

      // Disable the unsaved-changes warn before goto fires beforeNavigate.
      saved = true
      // Replace state so the user can't back-navigate into the now-stale
      // refine flow they just exited. /data_guide will refetch the saved
      // guide on its own.
      goto(`/generate/${project_id}/${task_id}/data_guide`, {
        replaceState: true,
      })
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Refine Data Guide"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    breadcrumbs={[
      {
        label: "Synthetic Data Generation",
        href: `/generate/${project_id}/${task_id}/synth`,
      },
      {
        label: "Data Guide",
        href: `/generate/${project_id}/${task_id}/data_guide`,
      },
    ]}
  >
    <DataGenDescription bind:guidance_data />

    {#if current_state === "loading" || current_state === "generating"}
      <AnalyzingAnimation
        title="Generating Examples"
        description="Generating synthetic data to test your data guide."
      />
    {:else if current_state === "preview"}
      <GuidePreview
        initial_examples_md={preview_initial_examples_md}
        initial_rules_md={preview_initial_rules_md}
        bind:examples_md
        bind:rules_md
        bind:error
        bind:submitting
        bind:reviewed_samples
        bind:general_feedback
        {saved}
        on:refine={handle_refine}
        on:save={handle_save}
      />
    {:else if current_state === "refining"}
      <RefiningAnimation
        title="Refining Data Guide"
        description="Kiln is refining your data guide with the feedback you provided and generating fresh examples to review. Hold tight!"
      />
    {:else if current_state === "regenerating"}
      <AnalyzingAnimation
        title="Regenerating Examples"
        description="Regenerating examples to review with your edited data guide. Hold tight!"
      />
    {:else if current_state === "load_error"}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="text-error text-sm">
          {error?.getMessage() ?? "An unknown error occurred"}
        </div>
      </div>
    {/if}
  </AppPage>
</div>
