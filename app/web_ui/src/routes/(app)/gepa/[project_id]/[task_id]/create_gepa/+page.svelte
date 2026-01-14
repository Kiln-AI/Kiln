<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import Completed from "$lib/ui/completed.svelte"
  import SavedRunConfigurationsDropdown from "$lib/ui/run_config_component/saved_run_configs_dropdown.svelte"
  import type { Task, TaskRunConfig, Eval, EvalConfig } from "$lib/types"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"
  import {
    get_task_composite_id,
    model_info,
    model_name,
    provider_name_from_id,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import {
    getDetailedModelName,
    getRunConfigPromptDisplayName,
  } from "$lib/utils/run_config_formatters"
  import CreateNewRunConfigDialog from "$lib/ui/run_config_component/create_new_run_config_dialog.svelte"
  import Output from "$lib/ui/output.svelte"
  import Warning from "$lib/ui/warning.svelte"

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
  let created_job: { id: string } | null = null

  let current_task: Task | null = null
  let task_loading = true

  type EvalWithConfig = {
    eval: Eval
    configs: EvalConfig[]
    current_config: EvalConfig | null
    has_default_config: boolean
    model_is_supported: boolean
    validation_status: "unchecked" | "checking" | "valid" | "invalid"
    validation_message: string | null
  }

  let evals_with_configs: EvalWithConfig[] = []
  let evals_loading = false
  let evals_error: KilnError | null = null

  let run_config_validation_status:
    | "unchecked"
    | "checking"
    | "valid"
    | "invalid" = "unchecked"
  let run_config_validation_message: string | null = null

  $: has_evals_without_config = evals_with_configs.some(
    (item) => !item.has_default_config,
  )
  $: has_unsupported_models =
    run_config_validation_status === "invalid" ||
    evals_with_configs.some(
      (item) => item.has_default_config && !item.model_is_supported,
    )
  $: is_validating =
    run_config_validation_status === "checking" ||
    evals_with_configs.some((item) => item.validation_status === "checking")
  $: submit_disabled =
    has_evals_without_config ||
    evals_loading ||
    has_unsupported_models ||
    is_validating ||
    run_config_validation_status === "unchecked" ||
    evals_with_configs.some((item) => item.validation_status === "unchecked") ||
    task_loading

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
      load_evals_and_configs(),
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

  async function load_evals_and_configs() {
    try {
      evals_loading = true
      evals_error = null

      const { data: evals_data, error: evals_fetch_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )

      if (evals_fetch_error) {
        throw evals_fetch_error
      }

      if (!evals_data) {
        evals_with_configs = []
        return
      }

      const evals_with_configs_promises = evals_data.map(async (evalItem) => {
        if (!evalItem.id) {
          throw new Error("Eval ID is missing")
        }

        const { data: configs_data, error: configs_error } = await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_configs",
          {
            params: {
              path: {
                project_id,
                task_id,
                eval_id: evalItem.id,
              },
            },
          },
        )

        if (configs_error) {
          throw configs_error
        }

        const current_config =
          (configs_data || []).find(
            (c) => c.id === evalItem.current_config_id,
          ) || null

        return {
          eval: evalItem,
          configs: configs_data || [],
          current_config,
          has_default_config: false,
          model_is_supported: false,
          validation_status: "unchecked" as const,
          validation_message: null,
        }
      })

      evals_with_configs = await Promise.all(evals_with_configs_promises)
    } catch (e) {
      evals_error = createKilnError(e)
    } finally {
      evals_loading = false
    }
  }

  async function check_run_config_validation() {
    if (!target_run_config_id) return

    try {
      run_config_validation_status = "checking"
      run_config_validation_message = null

      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/check_run_config",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
            query: {
              run_config_id: target_run_config_id,
            },
          },
        },
      )

      if (error) {
        throw error
      }

      if (data && !data.is_supported) {
        run_config_validation_status = "invalid"
        const run_config = get_selected_run_config(
          target_run_config_id,
          $run_configs_by_task_composite_id,
          project_id,
          task_id,
        )
        if (run_config) {
          const friendly_model = model_name(
            run_config.run_config_properties.model_name,
            $model_info,
          )
          const friendly_provider = provider_name_from_id(
            run_config.run_config_properties.model_provider_name,
          )
          run_config_validation_message = `${friendly_model} (${friendly_provider}) is not supported for GEPA`
        } else {
          run_config_validation_message = "Model is not supported for GEPA"
        }
      } else {
        run_config_validation_status = "valid"
        run_config_validation_message = null
      }
    } catch (e) {
      run_config_validation_status = "invalid"
      run_config_validation_message = createKilnError(e).getMessage()
    }
  }

  async function check_eval_validation(index: number) {
    const item = evals_with_configs[index]
    if (!item.eval.id) return

    try {
      evals_with_configs[index].validation_status = "checking"
      evals_with_configs[index].validation_message = null
      evals_with_configs = [...evals_with_configs]

      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/check_eval",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
            query: {
              eval_id: item.eval.id,
            },
          },
        },
      )

      if (error) {
        throw error
      }

      if (data) {
        evals_with_configs[index].has_default_config = data.has_default_config
        evals_with_configs[index].model_is_supported = data.model_is_supported

        // Construct friendly message
        if (!data.has_default_config) {
          evals_with_configs[index].validation_message =
            "Please set a default config for this evaluator"
          evals_with_configs[index].validation_status = "invalid"
        } else if (!data.model_is_supported) {
          const config = evals_with_configs[index].current_config
          if (config) {
            const friendly_model = model_name(config.model_name, $model_info)
            const friendly_provider = provider_name_from_id(
              config.model_provider,
            )
            evals_with_configs[index].validation_message =
              `${friendly_model} (${friendly_provider}) is not supported for GEPA`
          } else {
            evals_with_configs[index].validation_message =
              "Model is not supported for GEPA"
          }
          evals_with_configs[index].validation_status = "invalid"
        } else {
          evals_with_configs[index].validation_message = null
          evals_with_configs[index].validation_status = "valid"
        }
      }
    } catch (e) {
      evals_with_configs[index].validation_status = "invalid"
      evals_with_configs[index].validation_message =
        createKilnError(e).getMessage()
    }
    evals_with_configs = [...evals_with_configs]
  }

  $: if (
    target_run_config_id &&
    target_run_config_id !== "custom" &&
    target_run_config_id !== "__create_new_run_config__"
  ) {
    check_run_config_validation()
  } else {
    run_config_validation_status = "unchecked"
    run_config_validation_message = null
  }

  $: if (evals_with_configs.length > 0 && !evals_loading) {
    evals_with_configs.forEach((_, index) => {
      if (evals_with_configs[index].validation_status === "unchecked") {
        check_eval_validation(index)
      }
    })
  }

  onMount(async () => {
    await Promise.all([
      load_task(),
      load_task_prompts(project_id, task_id),
      load_task_run_configs(project_id, task_id),
      load_evals_and_configs(),
    ])
  })

  async function create_gepa_job() {
    try {
      create_job_loading = true
      created_job = null

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
        !("id" in response) ||
        typeof response.id !== "string"
      ) {
        throw new Error("Invalid response from server")
      }

      created_job = { id: response.id }
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
    title="New GEPA Optimization Job"
    subtitle="Optimize the prompt for the current task."
    breadcrumbs={[
      {
        label: "GEPA Prompt Optimization",
        href: `/gepa/${project_id}/${task_id}`,
      },
    ]}
  >
    {#if task_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if created_job}
      <Completed
        title="GEPA Job Created"
        subtitle="It will take a while to complete optimization."
        link={`/gepa/${project_id}/${task_id}/gepa_job/${created_job.id}`}
        button_text="View GEPA Job"
      />
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
        {submit_disabled}
        on:submit={create_gepa_job}
        bind:error={create_job_error}
        bind:submitting={create_job_loading}
      >
        <Warning
          large_icon
          outline
          warning_color="primary"
          warning_message="GEPA only supports OpenRouter, OpenAI, Gemini, and Anthropic providers. Ensure your run configuration and evaluators use one of these providers."
        />

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
            <div
              class="text-sm font-medium text-gray-500 mb-3 flex items-center gap-3"
            >
              Configuration Overview
              {#if run_config_validation_status === "checking"}
                <span class="loading loading-spinner loading-xs"></span>
              {:else if run_config_validation_status === "valid"}
                <span class="text-success text-sm">✓ Valid</span>
              {:else if run_config_validation_status === "invalid"}
                <span class="text-error text-sm">✗ Invalid</span>
              {/if}
            </div>

            {#if run_config_validation_message}
              <div
                class={`mb-3 border rounded-lg p-3 ${run_config_validation_status === "invalid" ? "bg-error/10 border-error/20" : "bg-info/10 border-info/20"}`}
              >
                <div
                  class={`text-sm ${run_config_validation_status === "invalid" ? "text-error" : "text-info"}`}
                >
                  {run_config_validation_message}
                </div>
              </div>
            {/if}

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

        <div class="mt-6">
          <div class="text-sm font-medium text-gray-500 mb-3">
            Evaluators Configuration
          </div>

          {#if evals_loading}
            <div class="flex justify-center items-center py-8">
              <div class="loading loading-spinner loading-md"></div>
            </div>
          {:else if evals_error}
            <div class="bg-error/10 border border-error/20 rounded-lg p-4">
              <div class="text-error text-sm">
                {evals_error.getMessage() || "Failed to load evaluators"}
              </div>
            </div>
          {:else if evals_with_configs.length === 0}
            <div class="bg-base-200 rounded-lg p-5 text-center text-gray-500">
              No evaluators configured for this task.
            </div>
          {:else}
            <div class="bg-base-200 rounded-lg p-5">
              <div class="space-y-4">
                {#each evals_with_configs as { eval: evalItem, current_config, has_default_config, model_is_supported, validation_status, validation_message }}
                  <div class="border-l-2 border-base-300 pl-4 py-2">
                    <div class="flex items-center justify-between mb-2">
                      <div class="flex items-center gap-3">
                        <div class="font-medium">{evalItem.name}</div>
                        {#if validation_status === "checking"}
                          <span class="loading loading-spinner loading-xs"
                          ></span>
                        {:else if !has_default_config}
                          <div
                            class="flex items-center gap-2 text-sm text-warning"
                          >
                            <span class="text-xl">⚠️</span>
                            <span>No default config</span>
                          </div>
                        {:else if !model_is_supported}
                          <span class="text-error text-sm"
                            >✗ Model not supported</span
                          >
                        {:else if validation_status === "valid"}
                          <span class="text-success text-sm">✓</span>
                        {/if}
                      </div>
                    </div>

                    {#if current_config}
                      <div class="ml-1 text-sm text-gray-500">
                        <div class="mb-1">
                          Default:
                          <span class="font-medium text-gray-700"
                            >{current_config.name}</span
                          >
                        </div>
                        <div class="flex gap-4 text-xs">
                          <div>
                            <span class="font-medium">Provider:</span>
                            {provider_name_from_id(
                              current_config.model_provider,
                            )}
                          </div>
                          <div>
                            <span class="font-medium">Model:</span>
                            {model_name(current_config.model_name, $model_info)}
                          </div>
                        </div>
                      </div>
                    {/if}

                    {#if validation_message}
                      <div
                        class={`ml-1 mt-2 text-xs ${!has_default_config || !model_is_supported ? "text-error" : "text-info"}`}
                      >
                        {validation_message}
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}
        </div>
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
