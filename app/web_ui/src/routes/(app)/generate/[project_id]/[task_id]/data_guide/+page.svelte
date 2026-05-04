<script lang="ts">
  // Refine flow: shown when the user already has a saved data guide and
  // revisits to iterate on it. Sister of /data_guide_setup which handles the
  // first-time creation flow. Components live in the data_guide_setup
  // directory and are imported across.
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, onDestroy } from "svelte"
  import { page } from "$app/stores"
  import { goto, pushState } from "$app/navigation"
  import GuideRefineView from "../data_guide_setup/guide_refine_view.svelte"
  import GuidePreview from "../data_guide_setup/guide_preview.svelte"
  import DataGenDescription from "../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../synth_data_guidance_datamodel"
  import type {
    KilnAgentRunConfigProperties,
    Task,
    DataGuide,
  } from "$lib/types"
  import { agentInfo } from "$lib/agent"
  import { current_task } from "$lib/stores"
  import AnalyzingAnimation from "$lib/ui/animations/analyzing_animation.svelte"
  import RefiningAnimation from "$lib/ui/animations/refining_animation.svelte"
  import DeleteDialog from "$lib/ui/delete_dialog.svelte"
  import { isMacOS } from "$lib/utils/platform"

  type GuideBuilderState =
    | "loading"
    | "refine_existing"
    | "generating"
    | "preview"
    | "refining"
    | "regenerating"

  // Start in "loading" so we can redirect away if no saved guide exists
  // (the setup flow lives at /data_guide_setup).
  let current_state: GuideBuilderState = "loading"
  let error: KilnError | null = null
  let submitting = false

  let guide: string = ""
  let saved_data_guide: DataGuide | null = null

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
  let task: Task | null = null
  // Bound so the AppPage's "Edit" action button can drive the dialog inside
  // GuideRefineView without having to lift the dialog state up here.
  let refine_view: GuideRefineView | null = null

  // --- Wizard journey nav ---
  // Same pattern as the setup page, minus the setup-form snapshot fields.
  type StableState = "refine_existing" | "preview"
  type JourneySnapshot = {
    state: StableState
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
  // Bumped on popstate so any async op in flight at the time can detect that
  // the user navigated away mid-call and abandon its push_step instead of
  // forcing them back to the result screen.
  let nav_token: number = 0

  function snapshot_state(state: StableState): JourneySnapshot {
    return {
      state,
      guide,
      preview_initial_guide,
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
    // No journey_index on the entry we're popping to — user backed out past
    // our pushed entries (typical when hitting back during a transient
    // generating/refining state, since those don't push their own history
    // entry). Cancel the in-flight visual state by snapping back to the
    // last stable snapshot.
    if (
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
    name: "Refine Data Guide",
    description: `Refine the saved task data guide for project ${project_id}, task ${task_id}.`,
  })

  onMount(async () => {
    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        { params: { path: { project_id, task_id } } },
      )
      if (data) {
        guide = data.guide
        saved_data_guide = data
      }
    } catch {
      // No existing guide
    }

    // No saved guide → send them to the setup flow.
    if (!guide.trim()) {
      goto(`/generate/${project_id}/${task_id}/data_guide_setup`)
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
        // Non-critical
      }
    }

    current_state = "refine_existing"
    push_step("refine_existing")
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
      current_state = "refine_existing"
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
      const { data: saved, error: api_error } = await client.PUT(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        {
          params: { path: { project_id, task_id } },
          body: {
            guide,
          },
        },
      )

      if (api_error) throw api_error

      // Refine page: stay here after save and drop the user back on the
      // saved-guide view with refreshed metadata. This is different from the
      // setup page, which redirects to /synth on first save.
      if (saved) {
        saved_data_guide = saved
        guide = saved.guide
      }
      current_state = "refine_existing"
      push_step("refine_existing")
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

  let delete_dialog: DeleteDialog | null = null
  $: delete_url = `/api/projects/${project_id}/tasks/${task_id}/data_gen_guide`
  function after_delete() {
    goto(`/generate/${project_id}/${task_id}/synth`)
  }
</script>

<!-- TODO: Update read the docs link to point to new data guide docs -->
<div class="max-w-[1400px]">
  <AppPage
    title={current_state === "refine_existing" || current_state === "loading"
      ? "Data Guide"
      : "Refine Data Guide"}
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    breadcrumbs={[
      {
        label: "Synthetic Data Generation",
        href: `/generate/${project_id}/${task_id}/synth`,
      },
    ]}
    action_buttons={current_state === "refine_existing"
      ? [
          {
            icon: "/images/delete.svg",
            handler: () => delete_dialog?.show(),
            shortcut: isMacOS() ? "Backspace" : "Delete",
          },
          {
            label: "Edit",
            handler: () => refine_view?.open_edit_dialog(),
          },
        ]
      : []}
  >
    <DataGenDescription bind:guidance_data />

    {#if current_state === "loading"}
      <div class="flex flex-col items-center justify-center py-24 gap-4">
        <span class="loading loading-spinner loading-lg text-primary" />
      </div>
    {:else if current_state === "refine_existing"}
      <GuideRefineView
        bind:this={refine_view}
        {project_id}
        {guide}
        {task}
        data_guide={saved_data_guide}
        bind:page_error={error}
        on:generate_preview={handle_generate_preview}
        on:save={handle_save_with_guide}
      />
    {:else if current_state === "generating"}
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

<DeleteDialog
  name="Data Guide"
  bind:this={delete_dialog}
  {delete_url}
  {after_delete}
/>
