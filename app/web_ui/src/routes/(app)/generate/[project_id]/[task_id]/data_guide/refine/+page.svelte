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
  import { goto, pushState } from "$app/navigation"
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

  let current_state: RefineState = "loading"
  let error: KilnError | null = null
  let submitting = false

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

  let captured_input_run_config: KilnAgentRunConfigProperties | null = null
  let captured_output_run_config: KilnAgentRunConfigProperties | null = null

  // --- Preview-iteration journey nav ---
  // Each preview render snapshots state and pushes a history entry so back/
  // forward steps through prior iterations. Transient states (generating /
  // refining / regenerating) are skipped.
  type JourneySnapshot = {
    guide: string
    preview_initial_guide: string
    preview_samples: PreviewSample[]
    reviewed_samples: ReviewedSample[]
    general_feedback: string
    captured_input_run_config: KilnAgentRunConfigProperties | null
    captured_output_run_config: KilnAgentRunConfigProperties | null
  }
  let journey: JourneySnapshot[] = []
  let journey_index: number = -1
  let restoring_from_history: boolean = false
  let nav_token: number = 0

  function snapshot_state(): JourneySnapshot {
    return {
      guide,
      preview_initial_guide,
      preview_samples: [...preview_samples],
      reviewed_samples: reviewed_samples.map((s) => ({ ...s })),
      general_feedback,
      captured_input_run_config,
      captured_output_run_config,
    }
  }

  function push_preview_step() {
    if (restoring_from_history) return
    const snap = snapshot_state()
    journey = [...journey.slice(0, journey_index + 1), snap]
    journey_index = journey.length - 1
    pushState(`#preview-${journey_index}`, { journey_index })
  }

  function restore_snapshot(idx: number) {
    if (idx < 0 || idx >= journey.length) return
    restoring_from_history = true
    const s = journey[idx]
    guide = s.guide
    preview_initial_guide = s.preview_initial_guide
    preview_samples = s.preview_samples
    reviewed_samples = s.reviewed_samples
    general_feedback = s.general_feedback
    captured_input_run_config = s.captured_input_run_config
    captured_output_run_config = s.captured_output_run_config
    current_state = "preview"
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
    // No journey_index — the user backed past our first pushed preview onto
    // the bare /refine URL. There's nothing to show here without a handoff,
    // so step back one more entry to land cleanly on /data_guide (where this
    // flow always starts). Avoids leaving an orphan /refine entry in history.
    submitting = false
    window.history.back()
  }

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

    guide = handoff.guide
    captured_input_run_config = handoff.input_run_config
    captured_output_run_config = handoff.output_run_config

    window.addEventListener("popstate", handle_popstate)

    await run_initial_preview()
  })

  onDestroy(() => {
    window.removeEventListener("popstate", handle_popstate)
  })

  async function run_initial_preview() {
    const op_token = nav_token
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
            guide,
            run_config_properties: captured_input_run_config,
            output_run_config_properties: captured_output_run_config,
            num_samples: 5,
          },
        },
      )

      if (api_error) throw api_error
      if (!data) throw new KilnError("No preview samples returned", null)

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
      push_preview_step()
    } catch (e) {
      if (nav_token !== op_token) return
      error = createKilnError(e)
      // Initial preview failed — bail back to the saved-guide view with the
      // error surfaced via the URL? Simpler: just bail; the user can retry.
      goto(`/generate/${project_id}/${task_id}/data_guide`, {
        replaceState: true,
      })
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
      push_preview_step()
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
          body: { guide },
        },
      )

      if (api_error) throw api_error

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

<!-- TODO: Update read the docs link to point to new data guide docs -->
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
      <!-- {#key} forces a clean remount when the journey index changes so
           back/forward through preview snapshots rebuilds the table and
           dialog state from the restored snapshot rather than reusing stale
           component state. -->
      {#key journey_index}
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
      {/key}
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
