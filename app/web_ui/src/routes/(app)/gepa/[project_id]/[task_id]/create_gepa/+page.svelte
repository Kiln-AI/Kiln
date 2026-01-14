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

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let token_budget: "light" | "medium" | "heavy" = "medium"
  let target_run_config_id: string | null = null

  let create_new_run_config_dialog: CreateNewRunConfigDialog | null = null

  $: if (target_run_config_id === "__create_new_run_config__") {
    create_new_run_config_dialog?.show()
  }

  function get_prompt_text_from_id(
    prompt_id: string | null | undefined,
  ): string | null {
    if (!prompt_id || !task_prompts) {
      return null
    }

    const saved_prompt = task_prompts.prompts.find((p) => p.id === prompt_id)
    if (saved_prompt?.prompt) {
      return saved_prompt.prompt
    }

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

  $: is_dynamic_prompt =
    selected_run_config?.run_config_properties.prompt_id && !prompt_text

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

  $: step_3_visible = run_config_validation_status === "valid"

  $: selected_run_config = get_selected_run_config(
    target_run_config_id,
    $run_configs_by_task_composite_id,
    project_id,
    task_id,
  )

  $: task_prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

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

  function refresh_evaluators() {
    evals_with_configs = evals_with_configs.map((item) => ({
      ...item,
      validation_status: "unchecked" as const,
      validation_message: null,
    }))
  }

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
    subtitle="Use GEPA to automatically optimize your prompt."
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
        submit_label="Run Optimization"
        {submit_disabled}
        on:submit={create_gepa_job}
        bind:error={create_job_error}
        bind:submitting={create_job_loading}
      >
        <div class="text-xl font-bold">Step 1: Select Token Budget</div>
        <div>
          <FormElement
            label="Token Budget"
            description="This determines the number of prompt candidates that the GEPA optimizer will consider."
            info_description="A higher budget will generally result in higher quality prompts, but will take longer to complete."
            inputType="select"
            id="token_budget"
            select_options={[
              ["light", "Light (6 prompt candidates)"],
              ["medium", "Medium (12 prompt candidates)"],
              ["heavy", "Heavy (18 prompt candidates)"],
            ]}
            bind:value={token_budget}
          />
        </div>

        <div class="text-xl font-bold">
          Step 2: Select Target Run Configuration
        </div>
        <div>
          <SavedRunConfigurationsDropdown
            title="Target Run Configuration"
            description="The run configuration (model, prompt, etc.) to use for the optimization."
            {project_id}
            {current_task}
            bind:selected_run_config_id={target_run_config_id}
            run_page={false}
            auto_select_default={false}
          />

          {#if selected_run_config}
            {#if run_config_validation_status === "checking"}
              <div class="flex items-center gap-2 text-sm text-gray-500 mt-2">
                <span class="loading loading-spinner loading-xs"></span>
                <span>Checking compatibility...</span>
              </div>
            {:else if run_config_validation_status === "valid"}
              <div class="mt-2">
                <span class="badge badge-success badge-sm badge-outline gap-1">
                  <span>✓</span>
                  <span>Compatible with GEPA</span>
                </span>
              </div>
            {:else if run_config_validation_status === "invalid"}
              <div
                class="bg-error/10 border border-error/20 rounded-lg p-4 mt-3"
              >
                <div class="text-error text-sm font-medium mb-2">
                  {run_config_validation_message}
                </div>
                <div class="text-sm text-gray-600">
                  GEPA only supports OpenRouter, OpenAI, Gemini, and Anthropic
                  providers. Please select a different run configuration or
                  <button
                    type="button"
                    class="link underline"
                    on:click={() => create_new_run_config_dialog?.show()}
                  >
                    create a new one
                  </button>
                  with a supported provider.
                </div>
              </div>
            {/if}
          {/if}
        </div>

        {#if step_3_visible && selected_run_config}
          <div class="text-xl font-bold">Step 3: Review Configuration</div>

          <div>
            <div class="text-sm font-medium text-gray-700 mb-2">
              Target Run Configuration
            </div>
            <div class="text-xs text-gray-500 mb-3">
              GEPA will optimize the prompt to maximize performance using this
              configuration.
            </div>

            <div class="bg-base-200 rounded-lg p-4">
              <div class="flex flex-wrap gap-x-6 gap-y-2 text-sm mb-4">
                <div>
                  <span class="text-gray-500">Name:</span>
                  <span class="font-medium ml-1"
                    >{selected_run_config.name}</span
                  >
                </div>
                <div>
                  <span class="text-gray-500">Model:</span>
                  <span class="font-medium ml-1"
                    >{getDetailedModelName(
                      selected_run_config,
                      $model_info,
                    )}</span
                  >
                </div>
                <div>
                  <span class="text-gray-500">Provider:</span>
                  <span class="font-medium ml-1"
                    >{provider_name_from_id(
                      selected_run_config.run_config_properties
                        .model_provider_name,
                    )}</span
                  >
                </div>
              </div>

              <div class="text-xs text-gray-500 mb-2">
                Prompt: {getRunConfigPromptDisplayName(
                  selected_run_config,
                  task_prompts,
                )} (starting point for optimization)
              </div>
              {#if is_dynamic_prompt}
                <div class="text-sm text-gray-600 italic">
                  This run configuration uses a prompt generator that creates
                  prompts at runtime.
                </div>
              {:else if prompt_text}
                <Output raw_output={prompt_text} max_height="300px" />
              {:else}
                <div class="text-sm text-gray-500 italic">
                  No prompt configured.
                </div>
              {/if}
            </div>
          </div>

          <div>
            <div
              class="text-sm font-medium text-gray-700 mb-2 flex items-center justify-between"
            >
              <div class="flex items-center gap-2">
                <span>Evaluator Judges</span>
                {#if evals_with_configs.length > 0}
                  <span class="badge badge-sm badge-outline"
                    >{evals_with_configs.length}</span
                  >
                {/if}
              </div>
              {#if evals_with_configs.length > 0}
                <button
                  type="button"
                  class="btn btn-xs btn-outline"
                  on:click={refresh_evaluators}
                  disabled={is_validating}
                >
                  {#if is_validating}
                    <span class="loading loading-spinner loading-xs"></span>
                  {:else}
                    ↻
                  {/if}
                  Refresh
                </button>
              {/if}
            </div>
            <div class="text-xs text-gray-500 mb-3">
              GEPA will optimize to maximize performance on each of these
              evaluators.
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
              <div class="bg-base-200 rounded-lg p-4 text-center text-gray-500">
                No evaluators configured for this task.
              </div>
            {:else}
              <div class="bg-base-200 rounded-lg p-4 space-y-3">
                {#each evals_with_configs as { eval: evalItem, current_config, has_default_config, model_is_supported, validation_status, validation_message }}
                  {@const spec_id = "legacy"}
                  {@const eval_url = `/specs/${project_id}/${task_id}/${spec_id}/${evalItem.id}`}
                  {@const eval_configs_url = `/specs/${project_id}/${task_id}/${spec_id}/${evalItem.id}/eval_configs`}
                  <div
                    class={`border-l-4 pl-3 py-2 ${
                      validation_status === "checking"
                        ? "border-gray-300"
                        : !has_default_config
                          ? "border-warning"
                          : !model_is_supported
                            ? "border-error"
                            : "border-success"
                    }`}
                  >
                    <div class="flex items-start justify-between gap-2">
                      <div class="flex-1">
                        <div class="flex items-center gap-2 mb-1">
                          {#if validation_status === "checking"}
                            <span class="loading loading-spinner loading-xs"
                            ></span>
                          {:else if !has_default_config}
                            <span class="text-warning text-sm">⚠</span>
                          {:else if !model_is_supported}
                            <span class="text-error text-sm">✗</span>
                          {:else}
                            <span class="text-success text-sm">✓</span>
                          {/if}
                          <a
                            href={eval_url}
                            target="_blank"
                            class="font-medium text-sm link hover:underline"
                          >
                            {evalItem.name}
                          </a>
                        </div>

                        {#if evalItem.description}
                          <div class="text-xs text-gray-600 mb-1">
                            {evalItem.description}
                          </div>
                        {/if}

                        {#if current_config}
                          <div class="text-xs text-gray-500">
                            Judge: {current_config.name} - {model_name(
                              current_config.model_name,
                              $model_info,
                            )} ({provider_name_from_id(
                              current_config.model_provider,
                            )})
                          </div>
                        {/if}

                        {#if validation_message}
                          <div class="text-xs text-gray-600 mt-1">
                            {validation_message}
                          </div>
                        {/if}

                        {#if !has_default_config}
                          <div class="mt-2">
                            <a
                              href={eval_configs_url}
                              target="_blank"
                              class="link underline text-xs text-primary"
                            >
                              → Set default judge
                            </a>
                          </div>
                        {:else if !model_is_supported}
                          <div class="mt-2">
                            <a
                              href={eval_configs_url}
                              target="_blank"
                              class="link underline text-xs text-primary"
                            >
                              → Change default judge
                            </a>
                          </div>
                        {/if}
                      </div>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
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
