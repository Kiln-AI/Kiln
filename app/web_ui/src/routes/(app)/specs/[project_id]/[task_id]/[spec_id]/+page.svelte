<script lang="ts">
  import PropertyList from "$lib/ui/property_list.svelte"
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount, tick } from "svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import EditablePriorityField from "../editable_priority_field.svelte"
  import EditableStatusField from "../editable_status_field.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import type {
    Spec,
    SpecStatus,
    Eval,
    Task,
    TaskRunConfig,
    EvalResultSummary,
    EvalProgress,
    Priority,
  } from "$lib/types"
  import { client } from "$lib/api_client"
  import TagPicker from "$lib/ui/tag_picker.svelte"
  import {
    capitalize,
    formatPriority,
    formatSpecType,
    formatEvalConfigName,
  } from "$lib/utils/formatters"
  import { model_info, load_model_info } from "$lib/stores"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
  import { load_task, get_task_composite_id } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import RunConfigComparisonTable from "$lib/components/run_config_comparison_table.svelte"
  import CreateNewRunConfigDialog from "$lib/ui/run_config_component/create_new_run_config_dialog.svelte"
  import { load_task_prompts } from "$lib/stores/prompts_store"
  import {
    updateSpecPriority as updateSpecPriorityUtil,
    updateSpecStatus as updateSpecStatusUtil,
    linkFromFilterId,
  } from "../spec_utils"
  import EditDialog from "$lib/ui/edit_dialog.svelte"
  import { goto } from "$app/navigation"
  import SpecPropertiesDisplay from "../spec_properties_display.svelte"
  import posthog from "posthog-js"

  // ### Spec Details Page ###

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: spec_id = $page.params.spec_id!

  let spec: Spec | null = null
  let spec_error: KilnError | null = null
  let spec_loading = true
  let tags_error: KilnError | null = null
  let current_tags: string[] = []
  let updating_priorities = false
  let updating_statuses = false
  let priorityField: EditablePriorityField | null = null
  let statusField: EditableStatusField | null = null

  let eval_progress: EvalProgress | null = null
  let eval_progress_loading = true
  let eval_progress_error: KilnError | null = null

  let evaluator: Eval | null = null
  let eval_error: KilnError | null = null
  let eval_loading = false

  let task: Task | null = null
  let task_error: KilnError | null = null
  let task_loading = false

  let run_configs_error: KilnError | null = null
  let run_configs_loading = false

  let score_summary: EvalResultSummary | null = null
  let score_summary_error: KilnError | null = null

  let error: KilnError | null = null
  let loading: boolean = false
  $: error =
    spec_error ||
    eval_progress_error ||
    eval_error ||
    task_error ||
    run_configs_error
  $: loading =
    spec_loading ||
    eval_progress_loading ||
    eval_loading ||
    task_loading ||
    run_configs_loading

  let eval_state:
    | "not_started"
    | "running"
    | "complete"
    | "complete_with_errors" = "not_started"
  let create_new_run_config_dialog: CreateNewRunConfigDialog | null = null
  let edit_dialog: EditDialog | null = null

  $: current_task_run_configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] || null

  $: if (spec) {
    current_tags = spec.tags || []
  }

  function getPriorityOptions(): OptionGroup[] {
    return [
      {
        options: [
          { label: "P0", value: 0 },
          { label: "P1", value: 1 },
          { label: "P2", value: 2 },
          { label: "P3", value: 3 },
        ],
      },
    ]
  }

  function getStatusOptions(): OptionGroup[] {
    return [
      {
        options: [
          { label: "Active", value: "active" },
          { label: "Future", value: "future" },
          { label: "Deprecated", value: "deprecated" },
          { label: "Archived", value: "archived" },
        ],
      },
    ]
  }

  async function updateSpecPriority(newPriority: number) {
    if (!spec?.id || spec.priority === newPriority || updating_priorities) {
      return
    }

    updating_priorities = true
    try {
      spec = await updateSpecPriorityUtil(
        project_id,
        task_id,
        spec,
        newPriority,
      )
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      updating_priorities = false
    }
  }

  async function updateSpecStatus(newStatus: SpecStatus) {
    if (!spec?.id || spec.status === newStatus || updating_statuses) {
      return
    }

    updating_statuses = true
    try {
      spec = await updateSpecStatusUtil(project_id, task_id, spec, newStatus)
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      updating_statuses = false
    }
  }

  function handlePriorityUpdate(spec: Spec, value: Priority) {
    updateSpecPriority(value)
  }

  function handleStatusUpdate(spec: Spec, value: SpecStatus) {
    updateSpecStatus(value)
  }

  $: has_eval = spec?.eval_id
  $: has_default_eval_config = evaluator && evaluator.current_config_id
  $: should_show_compare_table = has_eval && has_default_eval_config

  onMount(async () => {
    await tick()
    load_model_info()
    await load_spec()
    if (spec?.eval_id) {
      await Promise.all([
        load_eval_data(),
        load_task_data(),
        load_run_configs_data(),
        get_eval_progress(),
      ])
      if (evaluator?.current_config_id) {
        await load_score_summary()
      }
    }
  })

  async function load_spec() {
    try {
      spec_loading = true
      spec_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: { project_id, task_id, spec_id },
          },
        },
      )
      if (error) {
        throw error
      }
      spec = data
      current_tags = spec.tags || []
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      spec_loading = false
    }
  }

  async function load_eval_data() {
    if (!spec?.eval_id) return
    try {
      eval_loading = true
      eval_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id: spec.eval_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      evaluator = data
    } catch (error) {
      eval_error = createKilnError(error)
    } finally {
      eval_loading = false
    }
  }

  async function load_task_data() {
    try {
      task_loading = true
      task_error = null
      task = await load_task(project_id, task_id)
    } catch (error) {
      task_error = createKilnError(error)
    } finally {
      task_loading = false
    }
  }

  async function load_run_configs_data() {
    try {
      run_configs_loading = true
      run_configs_error = null
      await load_task_run_configs(project_id, task_id)
    } catch (error) {
      run_configs_error = createKilnError(error)
    } finally {
      run_configs_loading = false
    }
  }

  async function load_score_summary() {
    if (!spec?.eval_id || !evaluator?.current_config_id) return
    try {
      score_summary_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_config/{eval_config_id}/score_summary",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id: spec.eval_id,
              eval_config_id: evaluator.current_config_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      score_summary = data
    } catch (error) {
      score_summary_error = createKilnError(error)
    }
  }

  $: sorted_task_run_configs = current_task_run_configs
    ? sortTaskRunConfigs(current_task_run_configs, evaluator, score_summary)
    : []

  function sortTaskRunConfigs(
    configs: TaskRunConfig[] | null,
    evaluator: Eval | null,
    score_summary: EvalResultSummary | null,
  ): TaskRunConfig[] {
    if (!configs || !configs.length) return []

    return [...configs].sort((a, b) => {
      if (a.id === task?.default_run_config_id) return -1
      if (b.id === task?.default_run_config_id) return 1

      if (evaluator?.output_scores?.length && score_summary?.results) {
        const lastScoreKey = string_to_json_key(
          evaluator.output_scores[evaluator.output_scores.length - 1].name,
        )

        const scoreA =
          score_summary.results["" + a.id]?.[lastScoreKey]?.mean_score
        const scoreB =
          score_summary.results["" + b.id]?.[lastScoreKey]?.mean_score

        if (
          scoreA !== null &&
          scoreA !== undefined &&
          scoreB !== null &&
          scoreB !== undefined
        ) {
          return scoreB - scoreA
        }

        if (scoreA !== null && scoreA !== undefined) return -1
        if (scoreB !== null && scoreB !== undefined) return 1
      }

      return a.name.localeCompare(b.name)
    })
  }

  async function save_tags(tags: string[]) {
    try {
      if (!spec?.id) return
      tags_error = null
      const { data, error } = await client.PATCH(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: { project_id, task_id, spec_id: spec.id },
          },
          body: {
            tags: tags,
          },
        },
      )
      if (error) {
        throw error
      }
      spec = data
      current_tags = spec.tags || []
      posthog.capture("update_spec_tags", {
        num_tags: tags.length,
      })
    } catch (err) {
      tags_error = createKilnError(err)
    }
  }

  async function get_eval_progress() {
    if (!spec?.eval_id) return
    try {
      eval_progress_loading = true
      eval_progress = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/progress",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id: spec.eval_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      eval_progress = data
    } catch (error) {
      eval_progress_error = createKilnError(error)
    } finally {
      eval_progress_loading = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={`Spec: ${spec?.name ? `${spec.name}` : ""}`}
    subtitle="Use evals to measure how well your task meets this specification."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/evals-and-specs"
    breadcrumbs={[
      {
        label: "Specs & Evals",
        href: `/specs/${project_id}/${task_id}`,
      },
    ]}
    action_buttons={[
      {
        label: "Edit",
        disabled: loading || error !== null,
        handler: () => {
          edit_dialog?.show()
        },
      },
    ]}
  >
    {#if loading}
      <div class="flex justify-center items-center h-full">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    {:else if !spec}
      <div class="text-error text-sm">
        Failed to load spec, please refresh the page and try again.
      </div>
    {:else}
      <div class="grid grid-cols-1 lg:grid-cols-[1fr,auto] gap-12">
        <div class="grow max-w-[900px]">
          <SpecPropertiesDisplay
            spec_type={spec.properties.spec_type}
            properties={spec.properties}
          />
        </div>
        <div class="flex flex-col gap-4">
          <PropertyList
            title="Properties"
            properties={[
              {
                name: "ID",
                value: spec.id ?? "None",
              },
              {
                name: "Template",
                value: formatSpecType(spec.properties.spec_type),
              },
              {
                name: "Priority",
                value: formatPriority(spec.priority),
                use_custom_slot: true,
              },
              {
                name: "Status",
                value: capitalize(spec.status),
                use_custom_slot: true,
              },
              {
                name: "Eval ID",
                value: spec.eval_id || "None",
                link: spec.eval_id
                  ? `/specs/${project_id}/${task_id}/${spec_id}/${spec.eval_id}`
                  : undefined,
              },
              {
                name: "Eval Status",
                value: eval_progress
                  ? eval_progress.current_eval_method !== null
                    ? "Ready"
                    : ""
                  : "Loading...",
                value_with_link:
                  eval_progress?.current_eval_method === null && spec.eval_id
                    ? {
                        prefix: "Not Ready - ",
                        link_text: "Configure",
                        link: `/specs/${project_id}/${task_id}/${spec_id}/${spec.eval_id}`,
                      }
                    : undefined,
              },
              {
                name: "Eval Judge",
                value: eval_progress
                  ? eval_progress.current_eval_method
                    ? formatEvalConfigName(
                        eval_progress.current_eval_method,
                        $model_info,
                        true,
                      )
                    : "None"
                  : "Loading...",
                link: eval_progress?.current_eval_method
                  ? `/specs/${project_id}/${task_id}/${spec_id}/${spec.eval_id}/eval_configs`
                  : undefined,
              },
              {
                name: "Eval Dataset",
                value: eval_progress
                  ? eval_progress.dataset_size + " items"
                  : "Loading...",
                link: eval_progress
                  ? linkFromFilterId(
                      project_id,
                      task_id,
                      evaluator?.eval_set_filter_id,
                    )
                  : undefined,
              },
            ]}
          >
            <!-- @ts-ignore - PropertyList has custom_value slot but lacks $$Slots typing -->
            <svelte:fragment slot="custom_value" let:property>
              {#if property.name === "Priority"}
                <EditablePriorityField
                  bind:this={priorityField}
                  {spec}
                  options={getPriorityOptions()}
                  aria_label="Priority"
                  onUpdate={handlePriorityUpdate}
                  compact={true}
                  onOpen={() => {
                    statusField?.close()
                  }}
                />
              {:else if property.name === "Status"}
                <EditableStatusField
                  bind:this={statusField}
                  {spec}
                  options={getStatusOptions()}
                  aria_label="Status"
                  onUpdate={handleStatusUpdate}
                  compact={true}
                  onOpen={() => {
                    priorityField?.close()
                  }}
                />
              {/if}
            </svelte:fragment>
          </PropertyList>
          <div class="text-xl font-bold mt-8">Tags</div>
          {#if tags_error}
            <div class="text-error text-sm mb-2">
              {tags_error.getMessage() || "An unknown error occurred"}
            </div>
          {/if}
          <TagPicker
            tags={current_tags}
            tag_type="task_run"
            {project_id}
            {task_id}
            on:tags_changed={(event) => {
              save_tags(event.detail.current)
            }}
          />
        </div>
      </div>

      {#if has_eval && eval_progress?.current_eval_method === null && spec.eval_id}
        <div class="mt-8">
          <a
            href={`/specs/${project_id}/${task_id}/${spec_id}/${spec.eval_id}`}
            class="btn btn-primary w-full"
          >
            Configure Eval
          </a>
        </div>
      {:else if should_show_compare_table && evaluator}
        <div class="mt-8">
          <RunConfigComparisonTable
            {project_id}
            {task_id}
            {spec_id}
            eval_id={spec.eval_id || ""}
            {evaluator}
            {task}
            {sorted_task_run_configs}
            {score_summary}
            {score_summary_error}
            current_eval_config_id={evaluator?.current_config_id}
            bind:eval_state
            interactive={true}
            title="Compare Run Configurations"
            on_add_run_config={() => {
              create_new_run_config_dialog?.show()
            }}
            on_eval_complete={async () => {
              await load_score_summary()
            }}
          />
        </div>
      {/if}
    {/if}
  </AppPage>
</div>

<EditDialog
  bind:this={edit_dialog}
  name="Spec"
  patch_url={`/api/projects/${project_id}/tasks/${task_id}/specs/${spec_id}`}
  delete_url={`/api/projects/${project_id}/tasks/${task_id}/specs/${spec_id}`}
  after_delete={() => {
    goto(`/specs/${project_id}/${task_id}`)
  }}
  fields={[
    {
      label: "Spec Name",
      description: "A name to identify this spec.",
      api_name: "name",
      value: spec?.name || "",
      input_type: "input",
      max_length: 120,
    },
  ]}
/>

<CreateNewRunConfigDialog
  bind:this={create_new_run_config_dialog}
  subtitle="Compare multiple run configurations to find which one produces the highest scores on your eval dataset."
  {project_id}
  {task}
  new_run_config_created={async () => {
    await load_task_prompts(project_id, task_id, true)
  }}
/>
