<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import GuideSetupForm from "./guide_setup_form.svelte"
  import type { GuideSample, GuideRule } from "./guide_setup_form.svelte"
  import GuidePreview from "./guide_preview.svelte"
  import DataGenDescription from "../data_gen_description.svelte"
  import { SynthDataGuidanceDataModel } from "../synth_data_guidance_datamodel"
  import { onDestroy } from "svelte"
  import type { Task, KilnAgentRunConfigProperties } from "$lib/types"

  type GuideBuilderState =
    | "setup"
    | "generating"
    | "preview"
    | "refining"
    | "saving"

  let current_state: GuideBuilderState = "setup"
  let error: KilnError | null = null
  let submitting = false

  let guide_examples: GuideSample[] = []
  let guide_rules: GuideRule[] = []

  type PreviewSample = { input: string; output: string }
  let preview_samples: PreviewSample[] = []

  // Requirements string built from rules for API calls
  let requirements: string = ""
  let examples: string | null = null

  let setup_form: GuideSetupForm | null = null

  // Captured from the generate modal event, reused for refine
  let captured_run_config: KilnAgentRunConfigProperties | null = null

  let guidance_data: SynthDataGuidanceDataModel =
    new SynthDataGuidanceDataModel()
  onDestroy(() => {
    guidance_data.destroy()
  })

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  // Parse requirements markdown back into rules
  function parse_requirements_to_rules(req: string): GuideRule[] {
    if (!req.trim()) return []
    const rules: GuideRule[] = []
    const sections = req.split(/^## /m).filter((s) => s.trim())
    for (const section of sections) {
      const newline_index = section.indexOf("\n")
      if (newline_index === -1) {
        rules.push({ name: section.trim(), content: "" })
      } else {
        rules.push({
          name: section.slice(0, newline_index).trim(),
          content: section.slice(newline_index + 1).trim(),
        })
      }
    }
    return rules
  }

  onMount(async () => {
    try {
      const { data } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide",
        { params: { path: { project_id, task_id } } },
      )
      if (data) {
        requirements = data.requirements
        examples = data.examples ?? null
        guide_rules = parse_requirements_to_rules(data.requirements)

        if (data.guide_run_ids && data.guide_run_ids.length > 0) {
          const samples: GuideSample[] = []
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
          guide_examples = samples
        }
      }
    } catch {
      // No existing guide
    }
  })

  function build_requirements(): string {
    const markdown = setup_form?.build_requirements_markdown() ?? ""
    return markdown || "Generate diverse, realistic inputs for this task."
  }

  function build_requirements_with_examples(
    selected_examples: GuideSample[],
  ): string {
    let guidance = build_requirements()
    if (selected_examples.length > 0) {
      const example_text = selected_examples
        .map(
          (e, i) => `Example ${i + 1}:\nInput: ${e.input}\nOutput: ${e.output}`,
        )
        .join("\n\n")
      guidance = guidance
        ? `${guidance}\n\n## Reference Examples\n${example_text}`
        : `## Reference Examples\n${example_text}`
    }
    return guidance
  }

  async function handle_generate_preview(
    event: CustomEvent<{
      selected_examples: GuideSample[]
      run_config: KilnAgentRunConfigProperties
    }>,
  ) {
    error = null
    submitting = true
    current_state = "generating"

    try {
      const run_config = event.detail.run_config
      captured_run_config = run_config
      const guidance = build_requirements_with_examples(
        event.detail.selected_examples,
      )
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
      if (!captured_run_config) {
        throw new KilnError("No model configuration available", null)
      }
      const run_config = captured_run_config

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

      requirements = data.refined_requirements
      if (data.refined_examples !== undefined) {
        examples = data.refined_examples ?? null
      }

      const { data: preview_data, error: preview_error } = await client.POST(
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
        bind:this={setup_form}
        bind:guide_examples
        bind:guide_rules
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
        {guide_rules}
        {guide_examples}
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
