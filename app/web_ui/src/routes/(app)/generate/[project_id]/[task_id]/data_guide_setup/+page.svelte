<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, onDestroy } from "svelte"
  import { page } from "$app/stores"
  import { goto, pushState } from "$app/navigation"
  import GuideSetupForm, {
    type GuideSample,
    type GuideRule,
  } from "./guide_setup_form.svelte"
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
    | "synthesizing_initial"
    | "generating"
    | "preview"
    | "refining"
    | "regenerating"

  // Start in "loading" so we can redirect away if a saved guide already exists
  // (the refine flow lives at /data_guide). Without this we'd briefly flash
  // the setup form before the GET resolves.
  let current_state: GuideBuilderState = "loading"
  let error: KilnError | null = null
  let submitting = false

  // The single guide prompt string — the source of truth
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

  // Lifted out of GuideSetupForm so the user's examples/rules survive the
  // setup → generating → setup unmount cycle that happens when a preview
  // request fails.
  let guide_examples: GuideSample[] = []
  let guide_rules: GuideRule[] = []

  // --- Wizard journey nav ---
  // Each "user-visible" step (setup form or preview screen) snapshots the
  // page state and pushes a new history entry. popstate restores by index.
  // Only stable states get snapshotted — "loading" / "generating" /
  // "refining" / "regenerating" are transient and skipped.
  // Memory-only: a hard refresh resets the journey.
  type StableState = "setup" | "preview"
  type JourneySnapshot = {
    state: StableState
    guide: string
    preview_initial_guide: string
    guide_examples: GuideSample[]
    guide_rules: GuideRule[]
    preview_samples: PreviewSample[]
    reviewed_samples: ReviewedSample[]
    general_feedback: string
    captured_input_run_config: KilnAgentRunConfigProperties | null
    captured_output_run_config: KilnAgentRunConfigProperties | null
  }
  let journey: JourneySnapshot[] = []
  let journey_index: number = -1
  let restoring_from_history: boolean = false
  // Bumped on popstate so any async op in flight at the time can detect that
  // the user navigated away mid-call and abandon its push_step instead of
  // forcing them back to the result screen.
  let nav_token: number = 0

  function snapshot_state(state: StableState): JourneySnapshot {
    return {
      state,
      guide,
      preview_initial_guide,
      guide_examples: [...guide_examples],
      guide_rules: [...guide_rules],
      preview_samples: [...preview_samples],
      reviewed_samples: reviewed_samples.map((s) => ({ ...s })),
      general_feedback,
      captured_input_run_config,
      captured_output_run_config,
    }
  }

  function push_step(state: StableState) {
    if (restoring_from_history) return
    const snap = snapshot_state(state)
    journey = [...journey.slice(0, journey_index + 1), snap]
    journey_index = journey.length - 1
    pushState(`#${state}-${journey_index}`, { journey_index })
  }

  function restore_snapshot(idx: number) {
    if (idx < 0 || idx >= journey.length) return
    restoring_from_history = true
    const s = journey[idx]
    guide = s.guide
    preview_initial_guide = s.preview_initial_guide
    guide_examples = s.guide_examples
    guide_rules = s.guide_rules
    preview_samples = s.preview_samples
    reviewed_samples = s.reviewed_samples
    general_feedback = s.general_feedback
    captured_input_run_config = s.captured_input_run_config
    captured_output_run_config = s.captured_output_run_config
    current_state = s.state
    journey_index = idx
    Promise.resolve().then(() => {
      restoring_from_history = false
    })
  }

  function handle_popstate(event: PopStateEvent) {
    nav_token++
    const idx = (event.state as { journey_index?: number } | null)
      ?.journey_index
    if (typeof idx === "number") {
      restore_snapshot(idx)
      return
    }
    // No journey_index — user backed out past our pushed entries while a
    // transient generating/refining state was on screen. Snap back to the
    // last stable snapshot so the loading animation clears.
    if (
      current_state === "synthesizing_initial" ||
      current_state === "generating" ||
      current_state === "refining" ||
      current_state === "regenerating"
    ) {
      submitting = false
      if (journey_index >= 0) {
        restore_snapshot(journey_index)
      }
    }
  }

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
    // If a saved guide already exists, send the user to the refine page —
    // setup is for first-time creation only.
    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        { params: { path: { project_id, task_id } } },
      )
      if (data) {
        goto(`/generate/${project_id}/${task_id}/data_guide`)
        return
      }
    } catch {
      // No existing guide
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
        // Non-critical
      }
    }

    current_state = "setup"
    push_step("setup")
    window.addEventListener("popstate", handle_popstate)
  })

  onDestroy(() => {
    window.removeEventListener("popstate", handle_popstate)
  })

  async function handle_generate_preview(
    event: CustomEvent<{
      guide: string
      input_run_config: KilnAgentRunConfigProperties
      output_run_config: KilnAgentRunConfigProperties
    }>,
  ) {
    const op_token = nav_token
    error = null
    submitting = true

    try {
      captured_input_run_config = event.detail.input_run_config
      captured_output_run_config = event.detail.output_run_config
      guide = event.detail.guide

      // Bootstrap step: always run the metaprompter on first preview to
      // mine the task definition (instruction, description, JSON schemas)
      // and the user's reference examples for rules — even if the user has
      // hand-authored some rules in the setup form. The metaprompter is
      // instructed to carry their rules forward and only add new ones in
      // gaps (uncovered scope+type cells, schema-derived constraints, format
      // directives from the task instruction). Without this pass, the user's
      // authored rules go to preview as-is and they miss the task-mined +
      // schema-mined contributions until after a full rate/refine cycle.
      current_state = "synthesizing_initial"
      const { data: synth_data, error: synth_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_refine",
        {
          params: { path: { project_id, task_id } },
          body: {
            current_guide: guide,
            feedback: "",
            preview_samples: [],
            run_config_properties: captured_input_run_config,
          },
        },
      )

      if (synth_error) throw synth_error
      if (nav_token !== op_token) return
      if (synth_data?.refined_guide) {
        guide = synth_data.refined_guide
      }

      current_state = "generating"
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

      // If the user navigated back/forward during the API call, abandon the
      // result rather than yanking them back to a preview screen.
      if (nav_token !== op_token) return

      preview_samples = data as PreviewSample[]
      reviewed_samples = preview_samples.map((s) => ({
        input: s.input,
        output: s.output,
        looks_good: undefined,
      }))
      general_feedback = ""
      preview_initial_guide = guide
      current_state = "preview"
      push_step("preview")
    } catch (e) {
      if (nav_token !== op_token) return
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
    const op_token = nav_token
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

      // If the user navigated back/forward during the API call, abandon the
      // result rather than yanking them back to a preview screen.
      if (nav_token !== op_token) return

      preview_samples = preview_data as PreviewSample[]
      reviewed_samples = preview_samples.map((s) => ({
        input: s.input,
        output: s.output,
        looks_good: undefined,
      }))
      general_feedback = ""
      preview_initial_guide = guide
      current_state = "preview"
      push_step("preview")
    } catch (e) {
      if (nav_token !== op_token) return
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
</script>

<!-- TODO: Update read the docs link to point to new data guide docs -->
<div class="max-w-[1400px]">
  <AppPage
    title="Set Up Data Guide"
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
    {:else if current_state === "synthesizing_initial"}
      <RefiningAnimation
        title="Preparing Rules"
        description="Kiln is mining the task definition and your reference examples for rules — drafting new ones and carrying yours forward — before generating preview examples. Hold tight!"
      />
    {:else if current_state === "generating"}
      <AnalyzingAnimation
        title="Generating Examples"
        description="Kiln is generating synthetic examples using your data guide so you can review them. Hold tight!"
      />
    {:else if current_state === "preview"}
      <GuidePreview
        initial_guide={preview_initial_guide}
        bind:guide
        bind:error
        bind:submitting
        bind:reviewed_samples
        bind:general_feedback
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
    {/if}
  </AppPage>
</div>
