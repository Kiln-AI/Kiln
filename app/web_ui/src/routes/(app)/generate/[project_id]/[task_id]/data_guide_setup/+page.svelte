<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, onDestroy } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import GuideSetupForm, { type GuideSample } from "./guide_setup_form.svelte"
  import { pending_data_guide_example } from "./pending_example_store"
  import { get } from "svelte/store"
  import GuidePreview from "./guide_preview.svelte"
  import DataGenDescription from "../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../synth_data_guidance_datamodel"
  import type { KilnAgentRunConfigProperties, Task } from "$lib/types"
  import { agentInfo } from "$lib/agent"
  import { current_task } from "$lib/stores"
  import AnalyzingAnimation from "$lib/ui/animations/analyzing_animation.svelte"
  import RefiningAnimation from "$lib/ui/animations/refining_animation.svelte"

  type GuideBuilderState =
    | "loading"
    | "setup"
    | "generating"
    | "preview"
    | "refining"
    | "regenerating"
    | "load_error"

  // Start in "loading" so we can redirect away if a saved guide already exists
  // (the refine flow lives at /data_guide). Without this we'd briefly flash
  // the setup form before the GET resolves.
  let current_state: GuideBuilderState = "loading"
  let error: KilnError | null = null
  let submitting = false
  // Flipped true once the guide is saved and we're navigating away. Suppresses
  // GuidePreview's unsaved-changes warn so the post-save goto doesn't prompt.
  let saved = false

  // The full data guide markdown. Setup builds this from the user's
  // examples; refine rewrites it wholesale to incorporate generated rules.
  let guide: string = ""

  type PreviewSample = { input: string; output: string }
  type ReviewedSample = {
    input: string
    output: string
    looks_good: boolean | undefined
  }
  let preview_samples: PreviewSample[] = []
  let preview_initial_guide: string = ""
  let reviewed_samples: ReviewedSample[] = []
  let general_feedback: string = ""

  // Captured from the setup form so refine/regenerate can reuse them
  let captured_input_run_config: KilnAgentRunConfigProperties | null = null
  let captured_output_run_config: KilnAgentRunConfigProperties | null = null

  // The task being edited. Needed by the output run config dialog so it can
  // mirror the SDG output flow (prompt + tools/skills selectors at top level).
  let task: Task | null = null

  // Lifted out of GuideSetupForm so the user's examples survive the
  // setup → generating → setup unmount cycle that happens when a preview
  // request fails.
  let guide_examples: GuideSample[] = []

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
    // If a saved guide already exists, the user shouldn't be in the setup
    // flow — that's for first-time creation only. Edit/delete/re-verify
    // happens on the main /data_guide page.
    //
    // Distinguish "GET returned no guide" from "GET failed". A backend or
    // network error must NOT silently land the user on setup, where they
    // could overwrite an existing-but-currently-unreachable guide once the
    // server recovers.
    try {
      const { data, error: api_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        { params: { path: { project_id, task_id } } },
      )
      if (api_error) {
        error = createKilnError(api_error)
        current_state = "load_error"
        return
      }
      if (data) {
        goto(`/generate/${project_id}/${task_id}/data_guide`, {
          replaceState: true,
        })
        return
      }
    } catch (e) {
      error = createKilnError(e)
      current_state = "load_error"
      return
    }

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
        // Non-critical — `task` is bound nullable downstream and only feeds
        // optional UI (the output run config dialog). The setup form remains
        // usable without it.
      }
    }

    // Seed from the synth-page handoff: if the user clicked "Set Up Data
    // Guide" and added their first example via the dialog before navigating
    // here, that sample is sitting on a writable store. Pull it once and
    // clear so a hard refresh doesn't re-seed it.
    const seeded = get(pending_data_guide_example)
    if (seeded) {
      guide_examples = [seeded]
      pending_data_guide_example.set(null)
    }

    current_state = "setup"
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
      reviewed_samples = preview_samples.map((s) => ({
        input: s.input,
        output: s.output,
        looks_good: undefined,
      }))
      general_feedback = ""
      preview_initial_guide = guide
      current_state = "preview"
    } catch (e) {
      error = createKilnError(e)
      current_state = "setup"
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
      }

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
      reviewed_samples = preview_samples.map((s) => ({
        input: s.input,
        output: s.output,
        looks_good: undefined,
      }))
      general_feedback = ""
      preview_initial_guide = guide
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
          body: { guide },
        },
      )

      if (api_error) throw api_error

      // Disable the unsaved-changes warn before goto fires beforeNavigate.
      // Mirrors the prompt_form / skill_form `complete = true` pattern.
      saved = true

      // Replace the setup page in history rather than pushing onto it. The
      // user finished and shouldn't be able to back-navigate into the now-
      // completed setup flow (which would just redirect them straight to
      // the refine page anyway).
      goto(`/generate/${project_id}/${task_id}/synth?session_continued=true`, {
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
    title="Set Up Data Guide"
    subtitle="Your Data Guide will help us generate better synthetic data."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    breadcrumbs={[
      {
        label: "Synthetic Data Generation",
        href: `/generate/${project_id}/${task_id}/synth?session_continued=true`,
        // This page is a sub-flow of /synth — replace rather than push so
        // back from /synth returns to wherever the user originally came
        // from (cards page, spec page, etc.) instead of bouncing here.
        replace_state: true,
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
        bind:page_error={error}
        on:generate_preview={handle_generate_preview}
      />
    {:else if current_state === "generating"}
      <AnalyzingAnimation
        title="Generating Examples"
        description="Generating synthetic data to test your data guide."
      />
    {:else if current_state === "preview"}
      <GuidePreview
        initial_guide={preview_initial_guide}
        bind:guide
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
        description="Refining your data guide with the feedback you provided and generating fresh examples to review."
      />
    {:else if current_state === "regenerating"}
      <AnalyzingAnimation
        title="Regenerating Examples"
        description="Regenerating synthetic data to test your edited data guide."
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
