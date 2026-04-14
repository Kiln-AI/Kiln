<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { current_task } from "$lib/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"
  import GuideSetupForm from "./guide_setup_form.svelte"
  import GuidePreview from "./guide_preview.svelte"
  import DataGenDescription from "../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../synth_data_guidance_datamodel"
  import { onDestroy } from "svelte"
  import type { Task } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"

  type GuideBuilderState =
    | "setup"
    | "generating"
    | "preview"
    | "refining"
    | "saving"

  let current_state: GuideBuilderState = "setup"
  let error: KilnError | null = null
  let submitting = false

  let requirements: string = ""
  let examples: string | null = null

  type PreviewSample = { input: string; output: string }
  let preview_samples: PreviewSample[] = []
  let existing_guide_samples: PreviewSample[] = []

  // Examples provided by the user on the setup screen
  let user_provided_examples: PreviewSample[] = []

  let run_config_component: RunConfigComponent | null = null
  let captured_run_config: ReturnType<
    RunConfigComponent["run_options_as_run_config_properties"]
  > | null = null

  let task: Task | null = null

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  function get_run_config() {
    const run_config =
      run_config_component?.run_options_as_run_config_properties() ??
      captured_run_config
    if (!run_config) {
      throw new KilnError("Please select a model", null)
    }
    if (!isKilnAgentRunConfig(run_config)) {
      throw new KilnError(
        "Task Data Guide requires a kiln_agent run config",
        null,
      )
    }
    captured_run_config = run_config
    return run_config
  }

  onMount(async () => {
    task = $current_task

    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        { params: { path: { project_id, task_id } } },
      )
      if (data) {
        requirements = data.requirements
        examples = data.examples ?? null

        if (data.guide_run_ids && data.guide_run_ids.length > 0) {
          const samples: PreviewSample[] = []
          for (const run_id of data.guide_run_ids) {
            try {
              const { data: run_data } = await client.GET(
                "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}",
                {
                  params: {
                    path: { project_id, task_id, run_id },
                  },
                },
              )
              if (run_data) {
                samples.push({
                  input: run_data.input,
                  output: run_data.output?.output ?? "",
                })
              }
            } catch {
              // Skip missing runs
            }
          }
          existing_guide_samples = samples
        }
      }
    } catch {
      // No existing guide
    }
  })

  // Build the guidance text from user examples + optional requirements
  function build_requirements_from_examples(
    provided_examples: PreviewSample[],
  ): string {
    let guidance = requirements.trim()
    if (provided_examples.length > 0) {
      const example_text = provided_examples
        .map(
          (e, i) =>
            `Example ${i + 1}:\nInput: ${e.input}\nOutput: ${e.output}`,
        )
        .join("\n\n")
      guidance = guidance
        ? `${guidance}\n\n## Reference Examples\n${example_text}`
        : `## Reference Examples\n${example_text}`
    }
    return guidance || "Generate diverse, realistic inputs for this task."
  }

  async function handle_generate_preview(
    event: CustomEvent<{ selected_examples: PreviewSample[] }>,
  ) {
    error = null
    submitting = true
    current_state = "generating"
    user_provided_examples = event.detail.selected_examples

    try {
      const run_config = get_run_config()
      const guidance = build_requirements_from_examples(
        event.detail.selected_examples,
      )

      // Store the built guidance as requirements for future refinement
      requirements = guidance

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            requirements: guidance,
            examples,
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

  async function handle_generate_without_samples() {
    error = null
    submitting = true
    current_state = "generating"
    user_provided_examples = []

    try {
      const run_config = get_run_config()
      const guidance =
        requirements.trim() ||
        "Generate diverse, realistic inputs for this task."
      requirements = guidance

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            requirements: guidance,
            examples,
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
      const run_config = get_run_config()

      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_refine",
        {
          params: { path: { project_id, task_id } },
          body: {
            current_requirements: requirements,
            current_examples: examples,
            feedback: event.detail.feedback,
            preview_samples,
            run_config_properties: run_config,
          },
        },
      )

      if (api_error) throw api_error
      if (!data) throw new KilnError("No refinement returned", null)

      // Update requirements with refined version and loop back to preview
      requirements = data.refined_requirements
      if (data.refined_examples !== undefined) {
        examples = data.refined_examples ?? null
      }

      // Re-generate preview with refined guidance
      const {
        data: preview_data,
        error: preview_error,
      } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide_preview",
        {
          params: { path: { project_id, task_id } },
          body: {
            requirements,
            examples,
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
            requirements,
            examples,
            guide_run_ids: [],
            approved_samples: preview_samples,
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
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Synthetic Data Generation"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    action_buttons={[
      {
        label: "Back to Generate",
        href: `/generate/${project_id}/${task_id}/synth`,
      },
    ]}
  >
    <DataGenDescription bind:guidance_data />

    {#if current_state === "setup"}
      <GuideSetupForm
        bind:requirements
        bind:examples
        bind:error
        bind:submitting
        existing_samples={existing_guide_samples}
        {project_id}
        {task_id}
        on:generate_preview={handle_generate_preview}
        on:generate_without_samples={handle_generate_without_samples}
      >
        <svelte:fragment slot="model_selector">
          {#if task}
            <RunConfigComponent
              bind:this={run_config_component}
              {project_id}
              requires_structured_output={true}
              show_name_field={false}
              hide_prompt_selector={true}
              show_tools_selector_in_advanced={true}
              model_dropdown_settings={{
                requires_data_gen: true,
              }}
            />
          {/if}
        </svelte:fragment>
      </GuideSetupForm>
    {:else if current_state === "generating"}
      <div class="flex flex-col items-center justify-center py-24 gap-4">
        <span class="loading loading-spinner loading-lg text-primary" />
        <div class="text-gray-500">Generating synthetic examples...</div>
      </div>
    {:else if current_state === "preview"}
      <GuidePreview
        {preview_samples}
        {requirements}
        bind:error
        bind:submitting
        on:refine={handle_refine}
        on:save={handle_save}
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
