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
  import Warning from "$lib/ui/warning.svelte"
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
  } from "./input_examples_uploader.svelte"
  import { pending_data_guide_example } from "../data_guide_setup/pending_example_store"
  import posthog from "posthog-js"
  import DataGuideProRequired from "./data_guide_pro_required.svelte"
  import { checkKilnCopilotAvailable } from "$lib/utils/copilot_utils"

  type CopilotState =
    | "loading"
    | "pro_required"
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

    // Pro is required for the analyze endpoint. If the key isn't connected,
    // show the connect-Kiln-Pro card; the auth route returns the user here on
    // success.
    let pro_available = false
    try {
      pro_available = await checkKilnCopilotAvailable()
    } catch {
      pro_available = false
    }
    if (!pro_available) {
      current_state = "pro_required"
      return
    }

    current_state = "create"
  })

  function handle_entries_change(
    event: CustomEvent<{ entries: InputExampleEntry[] }>,
  ) {
    entries = event.detail.entries
  }

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
    const input_run_config: KilnAgentRunConfigProperties = rc

    submitting = true
    current_state = "analyzing"
    try {
      captured_input_run_config = input_run_config
      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/analyze_input_data_guide",
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
            task_description: task?.description ?? null,
            input_examples: entries.map((e) => e.text),
            num_preview_samples: 5,
            run_config_properties: input_run_config,
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
        entry_count: entries.length,
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
            num_samples: 5,
          },
        },
      )
      if (preview_error) throw preview_error
      if (!preview_data) throw new KilnError("No preview inputs returned", null)
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
          body: { guide },
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
    {:else if current_state === "pro_required"}
      <DataGuideProRequired />
    {:else if current_state === "create"}
      <FormContainer
        submit_label="Continue"
        on:submit={handle_analyze}
        bind:error
        bind:submitting
        submit_disabled={!has_entries}
        compact_button={true}
        warn_before_unload={has_entries}
      >
        <InputExamplesUploader
          {project_id}
          {task_id}
          {entries}
          on:change={handle_entries_change}
        />

        <RunOptionsTiles
          bind:this={run_options_tiles}
          mode="link"
          {project_id}
          {task}
        />

        {#if !has_entries}
          <div class="flex justify-end">
            <Warning
              warning_message="Add at least one example input to continue."
              warning_color="warning"
              warning_icon="exclaim"
              tight
            />
          </div>
        {/if}
      </FormContainer>
      <div class="flex justify-end mt-2">
        <button
          type="button"
          class="link text-sm text-gray-500 hover:text-gray-700"
          on:click={() => run_options_tiles?.open_combined_dialog()}
        >
          Generation options
        </button>
      </div>
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
