<script lang="ts">
  // Copilot path for creating an input data guide. New "create" step gathers
  // inputs (uploaded text docs + manual entries + selected task runs), then
  // calls the new copilot endpoint to seed an initial draft + preview. From
  // there we drop into the existing manual flow's preview/refine UI so the
  // post-seed experience is identical to the manual path.
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, onDestroy } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { get } from "svelte/store"
  import GuidePreview from "../data_guide_setup/guide_preview.svelte"
  import RunOptionsTiles from "../data_guide_setup/run_options_tiles.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import DataGenDescription from "../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../synth_data_guidance_datamodel"
  import type { KilnAgentRunConfigProperties, Task } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"
  import { agentInfo } from "$lib/agent"
  import { current_task } from "$lib/stores"
  import AnalyzingAnimation from "$lib/ui/animations/analyzing_animation.svelte"
  import RefiningAnimation from "$lib/ui/animations/refining_animation.svelte"
  import InputExamplesUploader, {
    type InputExampleEntry,
    MAX_EXAMPLE_LENGTH,
    MAX_TOTAL_ENTRIES,
  } from "./input_examples_uploader.svelte"
  import { pending_data_guide_example } from "../data_guide_setup/pending_example_store"
  import posthog from "posthog-js"
  import { checkKilnCopilotAvailable } from "$lib/utils/copilot_utils"
  import ConnectKilnCopilotSteps from "$lib/ui/kiln_copilot/connect_kiln_copilot_steps.svelte"
  import ExtractionDialog from "$lib/components/extraction_dialog.svelte"
  import type Dialog from "$lib/ui/dialog.svelte"

  // Tag used to scope the auto-extraction-on-submit popup. Mirrors the
  // constant in input_examples_uploader.svelte — uploaded docs and library
  // picks are both tagged with this so a single SSE run extracts them all.
  const DATA_GUIDE_DOC_TAG = "data_guide_example"

  type CopilotState =
    | "loading"
    | "connect"
    | "create"
    | "analyzing"
    | "preview"
    | "refining"
    | "regenerating"
    | "load_error"

  let current_state: CopilotState = "loading"
  let error: KilnError | null = null
  let submitting = false
  let saved = false
  // Set once the user finishes the Kiln Pro connect flow inline; flips the
  // connect card into its "Connected" state with a Continue button.
  let connect_success = false

  let entries: InputExampleEntry[] = []

  let guide: string = ""
  type PreviewSample = { input: string }
  type ReviewedSample = { input: string; looks_good: boolean | undefined }
  let preview_samples: PreviewSample[] = []
  let preview_initial_guide: string = ""
  let reviewed_samples: ReviewedSample[] = []
  let general_feedback: string = ""

  let captured_input_run_config: KilnAgentRunConfigProperties | null = null
  let refine_iterations = 0

  let task: Task | null = null
  let run_options_tiles: RunOptionsTiles | null = null

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Set Up Data Guide",
    description: `Use Kiln Pro to draft the input data guide for project ${project_id}, task ${task_id} from a list of example inputs.`,
  })

  $: has_entries = entries.length > 0

  onMount(async () => {
    // A fresh Kiln Pro OAuth callback (?code=...) must be handled by the inline
    // ConnectKilnCopilotSteps component — show the connect state immediately and
    // don't run the redirect/availability checks that would short-circuit it.
    const oauth_callback = new URLSearchParams(window.location.search).has(
      "code",
    )

    if (!oauth_callback) {
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

    // If the user added their first example via the synth-page intro and we
    // landed here through the chooser, seed it as a manual entry.
    const seeded = get(pending_data_guide_example)
    if (seeded?.input?.trim()) {
      entries = [
        {
          source: seeded.task_run_id ? "task_run" : "manual",
          label: seeded.task_run_id ? "Existing run" : "Manual 1",
          text: seeded.input,
        },
      ]
      pending_data_guide_example.set(null)
    }

    // Returning from OAuth — let the connect card finish the token exchange.
    if (oauth_callback) {
      current_state = "connect"
      return
    }

    // Pro is required for the analyze endpoint. If the key isn't connected,
    // show the connect-Kiln-Pro card inline.
    let pro_available = false
    try {
      pro_available = await checkKilnCopilotAvailable()
    } catch {
      pro_available = false
    }
    current_state = pro_available ? "create" : "connect"
  })

  function handle_connect_success() {
    connect_success = true
  }

  function proceed_after_connect() {
    connect_success = false
    current_state = "create"
  }

  function handle_entries_change(
    event: CustomEvent<{ entries: InputExampleEntry[] }>,
  ) {
    entries = event.detail.entries
  }

  let extraction_dialog: Dialog | null = null
  // True while the Continue-triggered extraction run is live. Bound from
  // ExtractionDialog so the Continue button can show progress and See All can
  // mark rows "Extracting…" after the user dismisses the run dialog.
  let extraction_running = false
  // Keep the Continue button spinning while a run is in flight, even after the
  // run dialog is dismissed.
  $: if (extraction_running) submitting = true

  async function handle_analyze() {
    error = null
    if (entries.length === 0) {
      error = new KilnError("Add at least one input example to continue.")
      return
    }
    const rc = run_options_tiles?.get_input_run_config()
    if (!rc || !isKilnAgentRunConfig(rc)) {
      error = new KilnError(
        "Pick a kiln_agent run config for input generation.",
      )
      return
    }
    captured_input_run_config = rc

    // Document entries are added without text — extraction is deferred to here.
    // If any are still pending, open the extractor picker; the run drives the
    // rest of the flow (hydrate text, then analyze) via handle_extraction_complete.
    const pending = entries.some(
      (e) => e.source === "document" && !e.text && !!e.document_id,
    )
    if (pending) {
      extraction_dialog?.show()
      return
    }

    try {
      await run_analyze()
    } catch (e) {
      error = createKilnError(e)
      current_state = "create"
    }
  }

  // Resolve text for document entries that don't have it yet. When the user
  // ran a specific extractor (extractor_config_id), prefer that extractor's
  // extraction — a doc can have several (one per extractor / RAG tool). Fall
  // back to the most recent extraction if there's no exact match.
  async function refresh_extractions(
    extractor_config_id?: string | null,
  ): Promise<InputExampleEntry[]> {
    const updated = await Promise.all(
      entries.map(async (e) => {
        if (e.source !== "document" || e.text || !e.document_id) return e
        try {
          const { data: extractions } = await client.GET(
            "/api/projects/{project_id}/documents/{document_id}/extractions",
            {
              params: {
                path: { project_id, document_id: e.document_id },
              },
            },
          )
          if (!extractions || extractions.length === 0) return e
          const matching = extractor_config_id
            ? extractions.filter((x) => x.extractor?.id === extractor_config_id)
            : []
          const pool = matching.length > 0 ? matching : extractions
          const chosen = [...pool].sort((a, b) =>
            (b.created_at || "").localeCompare(a.created_at || ""),
          )[0]
          if (!chosen) return e
          return {
            ...e,
            text: chosen.output_content,
            extraction_id: chosen.id,
          }
        } catch {
          return e
        }
      }),
    )
    entries = updated
    return updated
  }

  // The run finished (the dialog may already be closed). Hydrate the freshly
  // extracted entries; if any document still has no text it failed extraction —
  // surface a retryable error and stay in create rather than dropping it.
  // Otherwise continue straight into analyze.
  async function handle_extraction_complete(
    event: CustomEvent<{ extractor_config_id: string; error_count: number }>,
  ) {
    error = null
    const extractor_config_id = event.detail?.extractor_config_id
    try {
      const updated = await refresh_extractions(extractor_config_id)
      const still_pending = updated.filter(
        (e) => e.source === "document" && !e.text && !!e.document_id,
      )
      if (still_pending.length > 0) {
        submitting = false
        const n = still_pending.length
        error = new KilnError(
          `${n} document${n === 1 ? "" : "s"} couldn't be extracted. ` +
            `Click Continue to retry, or remove ${n === 1 ? "it" : "them"} from See All.`,
        )
        return
      }
      await run_analyze(updated.filter((e) => !!e.text))
    } catch (e) {
      error = createKilnError(e)
      current_state = "create"
      submitting = false
    }
  }

  // The run errored before completing (e.g. SSE stream failure). Mirror it onto
  // the Continue button so the user can retry — clicking Continue reopens the
  // picker and re-extracts only the still-pending docs.
  function handle_extraction_failed(
    event: CustomEvent<{ error: KilnError | null }>,
  ) {
    submitting = false
    error =
      event.detail?.error ??
      new KilnError("Document extraction failed. Click Continue to retry.")
  }

  // The run dialog was dismissed. If no run is live and we're still gathering
  // inputs, release the Continue button so the user can act again. (When a run
  // is live, or we've already advanced to analyze, leave state untouched.)
  function handle_extraction_dialog_closed() {
    if (!extraction_running && current_state === "create") {
      submitting = false
    }
  }

  async function run_analyze(override_entries?: InputExampleEntry[]) {
    const ready = (override_entries ?? entries).filter((e) => !!e.text)
    if (ready.length === 0) {
      throw new KilnError("No input examples with content to analyze.")
    }
    if (!captured_input_run_config) {
      throw new KilnError("Pick a kiln_agent run config for input generation.")
    }
    // Soft count cap: analyze only the first MAX_TOTAL_ENTRIES. Extra examples
    // are silently dropped here (the UI already warns when over the limit).
    const to_analyze = ready.slice(0, MAX_TOTAL_ENTRIES)
    // Hard length cap: block (don't truncate) when any analyzed example exceeds
    // the per-example limit — name the offenders so the user can fix them.
    const over_limit = to_analyze.filter(
      (e) => e.text.length > MAX_EXAMPLE_LENGTH,
    )
    if (over_limit.length > 0) {
      const names = over_limit.map((e) => e.label).join(", ")
      throw new KilnError(
        `${over_limit.length} example${over_limit.length === 1 ? "" : "s"} ` +
          `exceed the ${MAX_EXAMPLE_LENGTH.toLocaleString()} character limit ` +
          `(${names}). Remove or shorten ${over_limit.length === 1 ? "it" : "them"} to continue.`,
      )
    }
    submitting = true
    current_state = "analyzing"
    try {
      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/draft_input_data_guide",
        {
          params: { path: { project_id, task_id } },
          body: {
            target_task_info: {
              task_prompt: task?.instruction ?? "",
              task_input_schema: task?.input_json_schema
                ? JSON.stringify(task.input_json_schema)
                : "",
              task_output_schema: task?.output_json_schema
                ? JSON.stringify(task.output_json_schema)
                : "",
            },
            input_examples: to_analyze.map((e) => e.text),
            num_preview_samples: 5,
            run_config_properties: captured_input_run_config,
          },
        },
      )
      if (api_error) throw api_error
      if (!data) throw new KilnError("No draft guide returned", null)

      guide = data.draft_guide
      preview_samples = data.preview_samples as PreviewSample[]
      reviewed_samples = preview_samples.map((s) => ({
        input: s.input,
        looks_good: undefined,
      }))
      general_feedback = ""
      preview_initial_guide = guide
      current_state = "preview"
      posthog.capture("data_guide_copilot_analyzed", {
        entry_count: to_analyze.length,
      })
    } catch (e) {
      error = createKilnError(e)
      current_state = "create"
    } finally {
      submitting = false
    }
  }

  async function handle_refine(
    event: CustomEvent<{
      feedback: string
      rated_samples: { input: string; looks_good: boolean }[]
    }>,
  ) {
    error = null
    submitting = true
    const has_negative_feedback =
      event.detail.rated_samples.some((s) => !s.looks_good) ||
      event.detail.feedback.trim().length > 0
    current_state = has_negative_feedback ? "refining" : "regenerating"

    try {
      if (!captured_input_run_config) {
        throw new KilnError("No model configuration available", null)
      }
      let refined_guide = guide
      if (has_negative_feedback) {
        const { data, error: api_error } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_refine",
          {
            params: { path: { project_id, task_id } },
            body: {
              current_guide: guide,
              source: "kiln_pro",
              feedback: event.detail.feedback,
              preview_samples: event.detail.rated_samples,
              run_config_properties: captured_input_run_config,
            },
          },
        )
        if (api_error) throw api_error
        if (!data) throw new KilnError("No refinement returned", null)
        refined_guide = data.refined_guide
      }
      const { data: preview_data, error: preview_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            guide: refined_guide,
            run_config_properties: captured_input_run_config,
            num_samples: 5,
          },
        },
      )
      if (preview_error) throw preview_error
      if (!preview_data) throw new KilnError("No preview inputs returned", null)
      guide = refined_guide
      preview_samples = preview_data as PreviewSample[]
      reviewed_samples = preview_samples.map((s) => ({
        input: s.input,
        looks_good: undefined,
      }))
      general_feedback = ""
      preview_initial_guide = guide
      current_state = "preview"
      refine_iterations++
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
          body: { guide, source: "kiln_pro" },
        },
      )
      if (api_error) throw api_error
      saved = true
      posthog.capture("data_guide_saved", {
        method: "after_preview",
        source: "copilot",
        refine_iterations,
      })
      goto(
        `/generate/${project_id}/${task_id}/synth?session_continued=true&data_guide_saved=true`,
        { replaceState: true },
      )
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
    subtitle="Your Data Guide will help us generate better synthetic inputs."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    breadcrumbs={[
      {
        label: "Synthetic Data Generation",
        href: `/generate/${project_id}/${task_id}/synth?session_continued=true`,
        replace_state: true,
      },
    ]}
  >
    <DataGenDescription bind:guidance_data />

    {#if current_state === "loading"}
      <div class="flex flex-col items-center justify-center py-24 gap-4">
        <span class="loading loading-spinner loading-lg text-primary" />
      </div>
    {:else if current_state === "connect"}
      <div
        class="flex flex-col max-w-[400px] mx-auto mt-24 md:mt-36 border border-base-300 rounded-2xl bg-base-100 px-6 shadow-lg py-8 md:py-12"
      >
        <ConnectKilnCopilotSteps
          onSuccess={handle_connect_success}
          showCheckmark={connect_success}
        />
        {#if connect_success}
          <button
            class="btn btn-primary mt-4 btn-wide mx-auto"
            on:click={proceed_after_connect}
          >
            Continue
          </button>
        {/if}
      </div>
    {:else if current_state === "create"}
      <FormContainer
        submit_label="Continue"
        submitting_status={extraction_running ? "Extracting documents…" : ""}
        on:submit={handle_analyze}
        bind:error
        bind:submitting
        submit_disabled={!has_entries || extraction_running}
        compact_button={true}
        warn_before_unload={has_entries}
        submit_visible={has_entries}
      >
        <InputExamplesUploader
          {project_id}
          {task_id}
          {task}
          {entries}
          extraction_in_progress={extraction_running}
          on:change={handle_entries_change}
        />

        <RunOptionsTiles
          bind:this={run_options_tiles}
          mode="link"
          {project_id}
          {task}
        />
      </FormContainer>
      {#if has_entries}
        <div class="flex justify-end mt-2">
          <button
            type="button"
            class="link text-sm text-gray-500 hover:text-gray-700"
            on:click={() => run_options_tiles?.open_combined_dialog()}
          >
            Generation options
          </button>
        </div>
      {/if}
    {:else if current_state === "analyzing"}
      <AnalyzingAnimation
        title="Analyzing Inputs"
        description="Kiln Pro is analyzing your example inputs and drafting your data guide for review."
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
        description="Refining your data guide with the feedback you provided and generating fresh inputs to review."
      />
    {:else if current_state === "regenerating"}
      <AnalyzingAnimation
        title="Regenerating Inputs"
        description="Regenerating synthetic inputs to test your edited data guide."
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

<ExtractionDialog
  bind:dialog={extraction_dialog}
  bind:extracting={extraction_running}
  target_tags={[DATA_GUIDE_DOC_TAG]}
  preselect_default_extractor={true}
  on:extraction_complete={handle_extraction_complete}
  on:extraction_failed={handle_extraction_failed}
  on:close={handle_extraction_dialog_closed}
/>
