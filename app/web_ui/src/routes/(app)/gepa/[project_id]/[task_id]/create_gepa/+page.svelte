<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { goto } from "$app/navigation"
  import SavedRunConfigurationsDropdown from "$lib/ui/run_config_component/saved_run_configs_dropdown.svelte"
  import type { Task, TaskRunConfig } from "$lib/types"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"
  import { get_task_composite_id, model_info } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import {
    getDetailedModelName,
    getRunConfigPromptDisplayName,
  } from "$lib/utils/run_config_formatters"
  import Output from "$lib/ui/output.svelte"
  import CreateNewRunConfigDialog from "$lib/ui/run_config_component/create_new_run_config_dialog.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let token_budget: "light" | "medium" | "heavy" = "medium"
  let target_run_config_id: string | null = null

  let create_new_run_config_dialog: CreateNewRunConfigDialog | null = null

  $: if (target_run_config_id === "__create_new_run_config__") {
    create_new_run_config_dialog?.show()
  }

  let create_job_error: KilnError | null = null
  let create_job_loading = false
  let created_job_id: string | null = null

  let current_task: Task | null = null
  let task_loading = true

  $: selected_run_config = get_selected_run_config(
    target_run_config_id,
    $run_configs_by_task_composite_id,
    project_id,
    task_id,
  )

  $: task_prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

  function get_prompt_text_from_id(
    prompt_id: string | null | undefined,
  ): string | null {
    if (!prompt_id || !task_prompts) {
      return null
    }

    // Check if it's in the saved prompts first
    const saved_prompt = task_prompts.prompts.find((p) => p.id === prompt_id)
    if (saved_prompt?.prompt) {
      return saved_prompt.prompt
    }

    // If it's a generator ID, we can't show the text (it's generated at runtime)
    const is_generator = task_prompts.generators.some((g) => g.id === prompt_id)
    if (is_generator) {
      return null
    }

    return null
  }

  $: prompt_text =
    selected_run_config?.prompt?.prompt ||
    get_prompt_text_from_id(
      selected_run_config?.run_config_properties.prompt_id,
    )

  function get_selected_run_config(
    run_config_id: string | null,
    configs_by_task: Record<string, TaskRunConfig[]>,
    proj_id: string,
    tsk_id: string,
  ): TaskRunConfig | null {
    if (
      !run_config_id ||
      run_config_id === "custom" ||
      run_config_id === "__create_new_run_config__"
    ) {
      return null
    }
    const configs =
      configs_by_task[get_task_composite_id(proj_id, tsk_id)] || []
    return configs.find((config) => config.id === run_config_id) || null
  }

  onMount(async () => {
    await Promise.all([
      load_task(),
      load_task_prompts(project_id, task_id),
      load_task_run_configs(project_id, task_id),
    ])
  })

  async function load_task() {
    try {
      task_loading = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      current_task = data
    } catch (e) {
      create_job_error = createKilnError(e)
    } finally {
      task_loading = false
    }
  }

  async function create_gepa_job() {
    try {
      create_job_loading = true
      created_job_id = null

      if (
        !target_run_config_id ||
        target_run_config_id === "custom" ||
        target_run_config_id === "__create_new_run_config__"
      ) {
        throw new Error("Please select a saved run configuration")
      }

      const { data: response, error: post_error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/start",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
          body: {
            token_budget,
            target_run_config_id,
          },
        },
      )

      if (post_error) {
        throw post_error
      }
      if (
        !response ||
        typeof response !== "object" ||
        !("job_id" in response) ||
        typeof response.job_id !== "string"
      ) {
        throw new Error("Invalid response from server")
      }

      created_job_id = response.job_id as string

      goto(`/gepa/${project_id}/${task_id}/gepa_job/${created_job_id}`)
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        create_job_error = new KilnError("Could not create a GEPA job.", null)
      } else {
        create_job_error = createKilnError(e)
      }
    } finally {
      create_job_loading = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create a New GEPA Job"
    subtitle="Generate Eval Prompts and Augmented data."
    breadcrumbs={[{ label: "Tasks", href: `/tasks/${project_id}` }]}
  >
    {#if task_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if !current_task}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task</div>
        <div class="text-error text-sm">
          {create_job_error?.getMessage() || "Task not found"}
        </div>
      </div>
    {:else}
      <FormContainer
        submit_visible={true}
        submit_label="Start GEPA Job"
        on:submit={create_gepa_job}
        bind:error={create_job_error}
        bind:submitting={create_job_loading}
      >
        <div class="text-xl font-bold">Configure GEPA Job</div>

        <FormElement
          label="Token Budget"
          description="Select the token budget for this GEPA job. Light uses fewer tokens but is faster, Heavy uses more tokens but is more thorough."
          inputType="select"
          id="token_budget"
          select_options={[
            ["light", "Light"],
            ["medium", "Medium"],
            ["heavy", "Heavy"],
          ]}
          bind:value={token_budget}
        />

        <SavedRunConfigurationsDropdown
          title="Target Run Configuration"
          description="Select the run configuration to use for this GEPA job."
          {project_id}
          {current_task}
          bind:selected_run_config_id={target_run_config_id}
          run_page={false}
          auto_select_default={false}
        />

        {#if selected_run_config}
          <div class="mt-6">
            <div class="text-sm font-medium text-gray-500 mb-3">
              Configuration Overview
            </div>

            <div class="bg-base-200 rounded-lg p-5">
              <div class="flex flex-wrap gap-6 mb-5">
                <div class="flex-1 min-w-[180px]">
                  <div class="text-xs text-gray-500 mb-1">Name</div>
                  <div class="font-medium">{selected_run_config.name}</div>
                </div>

                <div class="flex-1 min-w-[180px]">
                  <div class="text-xs text-gray-500 mb-1">Model</div>
                  <div class="font-medium">
                    {getDetailedModelName(selected_run_config, $model_info)}
                  </div>
                </div>

                <div class="flex-1 min-w-[180px]">
                  <div class="text-xs text-gray-500 mb-1">Prompt</div>
                  <div class="font-medium">
                    {getRunConfigPromptDisplayName(
                      selected_run_config,
                      task_prompts,
                    )}
                  </div>
                </div>
              </div>

              <div class="flex flex-wrap gap-6">
                <div class="min-w-[100px]">
                  <div class="text-xs text-gray-500 mb-1">Temperature</div>
                  <div class="font-medium">
                    {selected_run_config.run_config_properties.temperature}
                  </div>
                </div>

                <div class="min-w-[100px]">
                  <div class="text-xs text-gray-500 mb-1">Top P</div>
                  <div class="font-medium">
                    {selected_run_config.run_config_properties.top_p}
                  </div>
                </div>

                {#if selected_run_config.run_config_properties.tools_config?.tools?.length}
                  <div class="min-w-[100px]">
                    <div class="text-xs text-gray-500 mb-1">Tools</div>
                    <div class="font-medium">
                      {selected_run_config.run_config_properties.tools_config
                        .tools.length} configured
                    </div>
                  </div>
                {/if}
              </div>

              {#if prompt_text}
                <div class="mt-5 pt-5 border-t border-base-300">
                  <div class="text-xs text-gray-500 mb-2">Prompt Text</div>
                  <Output raw_output={prompt_text} max_height="300px" />
                </div>
              {:else if selected_run_config.run_config_properties.prompt_id}
                <div class="mt-5 pt-5 border-t border-base-300">
                  <div class="text-xs text-gray-500 mb-2">Dynamic Prompt</div>
                  <div class="text-sm">
                    Uses {getRunConfigPromptDisplayName(
                      selected_run_config,
                      task_prompts,
                    )} generator to create prompts at runtime.
                  </div>
                </div>
              {/if}
            </div>
          </div>
        {/if}
      </FormContainer>
    {/if}
  </AppPage>
</div>

<CreateNewRunConfigDialog
  bind:this={create_new_run_config_dialog}
  {project_id}
  task={current_task}
  new_run_config_created={(run_config) => {
    target_run_config_id = run_config.id || null
  }}
  hide_tools_selector={true}
  on:close={() => {
    if (target_run_config_id === "__create_new_run_config__") {
      target_run_config_id = null
    }
  }}
/>
