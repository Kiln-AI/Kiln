<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
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
  import TagDropdown from "$lib/ui/tag_dropdown.svelte"
  import { checkKilnCopilotAvailable } from "$lib/utils/copilot_utils"
  import CopilotRequiredCard from "$lib/ui/kiln_copilot/copilot_required_card.svelte"

  function tagFromFilterId(filter_id: string): string | undefined {
    if (filter_id.startsWith("tag::")) {
      return filter_id.replace("tag::", "")
    }
    return undefined
  }

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  type TokenBudget = "light" | "medium" | "heavy"
  let token_budget: TokenBudget = "light"
  const token_budget_options: {
    value: TokenBudget
    title: string
    description: string
  }[] = [
    { value: "light", title: "Low", description: "6 prompt candidates" },
    { value: "medium", title: "Medium", description: "12 prompt candidates" },
    { value: "heavy", title: "High", description: "18 prompt candidates" },
  ]
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
  let kiln_copilot_connected: boolean | null = null
  let copilot_check_error: KilnError | null = null

  type EvalWithConfig = {
    eval: Eval
    configs: EvalConfig[]
    current_config: EvalConfig | null
    has_default_config: boolean
    has_train_set: boolean
    train_set_size: number | null
    model_is_supported: boolean
    validation_status: "unchecked" | "checking" | "valid" | "invalid"
    validation_message: string | null
  }

  let evals_with_configs: EvalWithConfig[] = []
  let evals_loading = false
  let evals_error: KilnError | null = null
  let selected_eval_ids: Set<string> = new Set()

  let train_set_tags: Record<string, string> = {} // eval_id -> tag name
  let saving_train_set: Record<string, boolean> = {} // eval_id -> is_saving
  let train_set_errors: Record<string, string> = {} // eval_id -> error_message
  let showing_train_set_picker: Record<string, boolean> = {} // eval_id -> showing picker

  let run_config_validation_status:
    | "unchecked"
    | "checking"
    | "valid"
    | "invalid" = "unchecked"
  let run_config_validation_message: string | null = null
  let run_config_blocking_reason:
    | "has_tools"
    | "unsupported_model"
    | "other"
    | null = null

  $: has_evals_without_config = evals_with_configs.some(
    (item) =>
      item.eval.id &&
      selected_eval_ids.has(item.eval.id) &&
      !item.has_default_config,
  )
  $: has_evals_without_train_set = evals_with_configs.some(
    (item) =>
      item.eval.id &&
      selected_eval_ids.has(item.eval.id) &&
      !item.has_train_set,
  )
  $: has_unsupported_models =
    run_config_validation_status === "invalid" ||
    evals_with_configs.some(
      (item) =>
        item.eval.id &&
        selected_eval_ids.has(item.eval.id) &&
        item.has_default_config &&
        !item.model_is_supported,
    )
  $: is_validating =
    run_config_validation_status === "checking" ||
    evals_with_configs.some(
      (item) =>
        item.eval.id &&
        selected_eval_ids.has(item.eval.id) &&
        item.validation_status === "checking",
    )
  $: submit_disabled =
    selected_eval_ids.size === 0 ||
    has_evals_without_config ||
    has_evals_without_train_set ||
    evals_loading ||
    has_unsupported_models ||
    is_validating ||
    run_config_validation_status === "unchecked" ||
    evals_with_configs.some(
      (item) =>
        item.eval.id &&
        selected_eval_ids.has(item.eval.id) &&
        item.validation_status === "unchecked",
    ) ||
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

  let from_prompt_generators: boolean = false

  onMount(async () => {
    from_prompt_generators =
      $page.url.searchParams.get("from") === "prompt_generators"

    try {
      kiln_copilot_connected = await checkKilnCopilotAvailable()
    } catch (e) {
      copilot_check_error = createKilnError(e)
      kiln_copilot_connected = false
    }

    if (kiln_copilot_connected) {
      await Promise.all([
        load_task(),
        load_task_prompts(project_id, task_id),
        load_task_run_configs(project_id, task_id),
        load_evals_and_configs(),
      ])
    }
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
          has_train_set: false,
          train_set_size: null,
          model_is_supported: false,
          validation_status: "unchecked" as const,
          validation_message: null,
        }
      })

      evals_with_configs = await Promise.all(evals_with_configs_promises)

      selected_eval_ids = new Set(
        evals_with_configs
          .map((item) => item.eval.id)
          .filter((id): id is string => id !== null && id !== undefined),
      )
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
      run_config_blocking_reason = null

      const run_config = get_selected_run_config(
        target_run_config_id,
        $run_configs_by_task_composite_id,
        project_id,
        task_id,
      )

      if (
        run_config?.run_config_properties.tools_config &&
        run_config?.run_config_properties.tools_config.tools.length > 0
      ) {
        run_config_validation_status = "invalid"
        run_config_validation_message =
          "Tools are not supported for Kiln Prompt Optimization"
        run_config_blocking_reason = "has_tools"
        return
      }

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
        run_config_blocking_reason = "unsupported_model"
        if (run_config) {
          const friendly_model = model_name(
            run_config.run_config_properties.model_name,
            $model_info,
          )
          const friendly_provider = provider_name_from_id(
            run_config.run_config_properties.model_provider_name,
          )
          run_config_validation_message = `${friendly_model} (${friendly_provider}) is not supported for Kiln Prompt Optimization`
        } else {
          run_config_validation_message =
            "Model is not supported for Kiln Prompt Optimization"
        }
      } else {
        run_config_validation_status = "valid"
        run_config_validation_message = null
        run_config_blocking_reason = null
      }
    } catch (e) {
      run_config_validation_status = "invalid"
      run_config_validation_message = createKilnError(e).getMessage()
      run_config_blocking_reason = "other"
    }
  }

  async function check_eval_validation(
    index: number,
    run_even_if_unselected = false,
  ) {
    const item = evals_with_configs[index]
    if (!item.eval.id) return

    if (!run_even_if_unselected && !selected_eval_ids.has(item.eval.id)) {
      return
    }

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
        evals_with_configs[index].has_train_set = data.has_train_set
        evals_with_configs[index].model_is_supported = data.model_is_supported

        // If has train set, fetch the size
        if (data.has_train_set && item.eval.train_set_filter_id) {
          const train_tag = tagFromFilterId(item.eval.train_set_filter_id)
          if (train_tag) {
            try {
              const { data: tag_counts, error: tag_error } = await client.GET(
                "/api/projects/{project_id}/tasks/{task_id}/tags",
                {
                  params: {
                    path: {
                      project_id,
                      task_id,
                    },
                  },
                },
              )
              if (tag_error) {
                throw tag_error
              }
              evals_with_configs[index].train_set_size =
                tag_counts?.[train_tag] || 0
            } catch (_) {
              evals_with_configs[index].train_set_size = 0
            }
          }
        }

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
              `${friendly_model} (${friendly_provider}) is not supported for Kiln Prompt Optimization`
          } else {
            evals_with_configs[index].validation_message =
              "Model is not supported for Kiln Prompt Optimization"
          }
          evals_with_configs[index].validation_status = "invalid"
        } else if (!data.has_train_set) {
          evals_with_configs[index].validation_message =
            "This eval requires a training set to use as examples during optimization."
          evals_with_configs[index].validation_status = "invalid"
        } else if (
          evals_with_configs[index].train_set_size !== null &&
          evals_with_configs[index].train_set_size === 0
        ) {
          const train_tag = tagFromFilterId(item.eval.train_set_filter_id || "")
          evals_with_configs[index].validation_message =
            `The train set is empty. Add data to the tag "${train_tag}" to use it for optimization.`
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
    if (
      evals_with_configs[index].validation_status === "invalid" &&
      item.eval.id
    ) {
      selected_eval_ids = new Set(
        [...selected_eval_ids].filter((id) => id !== item.eval.id),
      )
    }
  }

  async function save_train_set_for_eval(eval_id: string, tag: string) {
    if (!tag || tag.trim().length === 0) {
      train_set_errors[eval_id] = "Tag cannot be empty"
      train_set_errors = { ...train_set_errors }
      return
    }

    try {
      saving_train_set[eval_id] = true
      saving_train_set = { ...saving_train_set }
      train_set_errors[eval_id] = ""
      train_set_errors = { ...train_set_errors }

      const cleaned_tag = tag.trim().replace(/\s+/g, "_")
      const train_set_filter_id = `tag::${cleaned_tag}`

      const { error } = await client.PATCH(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}",
        {
          params: {
            path: {
              project_id,
              task_id,
              eval_id,
            },
          },
          body: {
            train_set_filter_id,
          },
        },
      )

      if (error) {
        throw error
      }

      // Clear the input and hide the picker
      train_set_tags[eval_id] = ""
      showing_train_set_picker[eval_id] = false
      train_set_tags = { ...train_set_tags }
      showing_train_set_picker = { ...showing_train_set_picker }

      // Find the eval index and re-check validation
      const index = evals_with_configs.findIndex(
        (item) => item.eval.id === eval_id,
      )
      if (index !== -1) {
        // Update the eval object with the new train_set_filter_id
        evals_with_configs[index].eval.train_set_filter_id = train_set_filter_id
        evals_with_configs = [...evals_with_configs]
        await check_eval_validation(index, true)
      }
    } catch (e) {
      train_set_errors[eval_id] =
        createKilnError(e).getMessage() || "Failed to save train set"
      train_set_errors = { ...train_set_errors }
    } finally {
      saving_train_set[eval_id] = false
      saving_train_set = { ...saving_train_set }
    }
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
    run_config_blocking_reason = null
  }

  $: if (evals_with_configs.length > 0 && !evals_loading) {
    evals_with_configs.forEach((_, index) => {
      const item = evals_with_configs[index]
      if (
        item.eval.id &&
        selected_eval_ids.has(item.eval.id) &&
        item.validation_status === "unchecked"
      ) {
        check_eval_validation(index)
      }
    })
  }

  async function refresh_evaluators() {
    const { data: evals_data } = await client.GET(
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

    if (evals_data) {
      const evals_by_id = new Map(evals_data.map((e) => [e.id, e]))
      const configs_by_eval_id = await Promise.all(
        evals_with_configs.map(async (item) => {
          const eval_id = item.eval.id
          if (!eval_id) return { eval_id: null as string | null, configs: [] }
          const { data: configs_data } = await client.GET(
            "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/eval_configs",
            {
              params: {
                path: {
                  project_id,
                  task_id,
                  eval_id,
                },
              },
            },
          )
          const configs = configs_data || []
          return { eval_id, configs }
        }),
      )
      evals_with_configs = evals_with_configs.map((item, i) => {
        const fresh_eval = item.eval.id ? evals_by_id.get(item.eval.id) : null
        const { configs } = configs_by_eval_id[i] ?? { configs: [] }
        const eval_obj = fresh_eval ?? item.eval
        const current_config =
          (configs.find((c) => c.id === eval_obj.current_config_id) as
            | EvalConfig
            | undefined) ?? null
        return {
          ...item,
          eval: eval_obj,
          configs,
          current_config,
          validation_status: "unchecked" as const,
          validation_message: null,
        }
      })
    } else {
      evals_with_configs = evals_with_configs.map((item) => ({
        ...item,
        validation_status: "unchecked" as const,
        validation_message: null,
      }))
    }

    await Promise.all(
      evals_with_configs.map((_, i) => check_eval_validation(i, true)),
    )
  }

  async function create_gepa_job() {
    try {
      create_job_loading = true
      created_job = null
      create_job_error = null

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
            eval_ids: Array.from(selected_eval_ids),
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
        create_job_error = new KilnError(
          "Could not create a Kiln Prompt Optimization job.",
          null,
        )
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
    title="Create Optimized Prompt"
    subtitle="Create a prompt optimized for your evals using training data."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/prompts/automatic-prompt-optimizer"
    breadcrumbs={from_prompt_generators
      ? [
          {
            label: "Optimize",
            href: `/optimize/${project_id}/${task_id}`,
          },
          {
            label: "Prompts",
            href: `/prompts/${project_id}/${task_id}`,
          },
          {
            label: "Prompt Generators",
            href: `/prompts/${project_id}/${task_id}/prompt_generators`,
          },
        ]
      : [
          {
            label: "Optimize",
            href: `/optimize/${project_id}/${task_id}`,
          },
          {
            label: "Prompts",
            href: `/prompts/${project_id}/${task_id}`,
          },
          {
            label: "Optimizer Jobs",
            href: `/gepa/${project_id}/${task_id}`,
          },
        ]}
  >
    {#if kiln_copilot_connected === null}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if kiln_copilot_connected === false}
      <CopilotRequiredCard
        description="Kiln Prompt Optimization requires Kiln Copilot to automatically optimize your prompts using advanced techniques."
        auth_url="/gepa/copilot_auth"
        back_label="Back to Optimizer Jobs"
        error={copilot_check_error}
      />
    {:else if task_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if created_job}
      <Completed
        title="Prompt Optimization Job Started"
        subtitle="It will take a while to complete optimization (could take up to several hours depending on the token budget, number of evaluators and examples)."
        link={`/gepa/${project_id}/${task_id}/gepa_job/${created_job.id}`}
        button_text="View Job"
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
        <div class="flex flex-col gap-12">
          <div>
            <div class="flex flex-col gap-1">
              <div class="text-xl font-bold flex justify-between items-center">
                Step 1: Select Token Budget
                <span class="font-normal">
                  <InfoTooltip
                    tooltip_text="A higher budget will generally result in higher quality prompts, but will take longer to complete."
                  />
                </span>
              </div>
              <div class="text-xs text-gray-500">
                This determines the number of prompt candidates that the Kiln
                Prompt Optimizer will consider.
              </div>
            </div>
            <div class="flex flex-col gap-3 mt-4">
              {#each token_budget_options as option}
                <label class="flex items-start gap-3 cursor-pointer group">
                  <input
                    type="radio"
                    name="token_budget"
                    class="radio mt-0.5"
                    checked={token_budget === option.value}
                    on:change={() => {
                      token_budget = option.value
                    }}
                  />
                  <div class="flex flex-col">
                    <span class="font-medium text-sm">{option.title}</span>
                    <span class="text-xs text-gray-500"
                      >{option.description}</span
                    >
                  </div>
                </label>
              {/each}
            </div>
          </div>

          <div>
            <div class="flex flex-col gap-1 mb-4">
              <div class="text-xl font-bold flex justify-between items-center">
                <div class="text-xl font-bold">
                  Step 2: Select Run Configuration
                </div>
                <span class="font-normal">
                  <InfoTooltip
                    tooltip_text="Kiln Prompt Optimization only supports OpenRouter, OpenAI, Gemini, and Anthropic providers."
                  />
                </span>
              </div>
              <div class="text-xs text-gray-500">
                The configuration to use when running the task during prompt
                optimization.
              </div>
            </div>
            <SavedRunConfigurationsDropdown
              title=""
              {project_id}
              {current_task}
              bind:selected_run_config_id={target_run_config_id}
              run_page={false}
              auto_select_default={false}
            />

            {#if selected_run_config}
              {#if run_config_validation_status === "checking"}
                <div class="flex items-center gap-2 text-sm text-gray-500 mt-4">
                  <span class="loading loading-spinner loading-xs"></span>
                  <span>Checking compatibility...</span>
                </div>
              {:else if run_config_validation_status === "invalid"}
                <div class="mt-3">
                  <Warning warning_color="error" outline={true}>
                    <div>
                      <div class="text-error font-medium">
                        {run_config_validation_message}
                      </div>
                      {#if run_config_blocking_reason !== "other"}
                        <div class="mt-2 text-gray-600">
                          {#if run_config_blocking_reason === "has_tools"}
                            Kiln Prompt Optimization does not support run
                            configurations that use tools. Please select a
                            different run configuration or
                            <button
                              type="button"
                              class="link underline"
                              on:click={() =>
                                create_new_run_config_dialog?.show()}
                            >
                              create a new one
                            </button>
                            without tools configured.
                          {:else if run_config_blocking_reason === "unsupported_model"}
                            Kiln Prompt Optimization only supports OpenRouter,
                            OpenAI, Gemini, and Anthropic providers. Please
                            select a different run configuration or
                            <button
                              type="button"
                              class="link underline"
                              on:click={() =>
                                create_new_run_config_dialog?.show()}
                            >
                              create a new one
                            </button>
                            with a supported provider.
                          {/if}
                        </div>
                      {/if}
                    </div>
                  </Warning>
                </div>
              {/if}
            {/if}
          </div>

          {#if step_3_visible && selected_run_config}
            <div>
              <div class="flex flex-col gap-1">
                <div class="text-xl font-bold">
                  Step 3: Review Configuration
                </div>
                <div class="text-xs text-gray-500">
                  Kiln Prompt Optimization will optimize the prompt to maximize
                  performance using this configuration.
                </div>
              </div>
            </div>

            <div>
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
                  {#if selected_run_config.run_config_properties.temperature !== undefined && selected_run_config.run_config_properties.temperature !== null}
                    <div>
                      <span class="text-gray-500">Temperature:</span>
                      <span class="font-medium ml-1"
                        >{selected_run_config.run_config_properties
                          .temperature}</span
                      >
                    </div>
                  {/if}
                  {#if selected_run_config.run_config_properties.top_p !== undefined && selected_run_config.run_config_properties.top_p !== null}
                    <div>
                      <span class="text-gray-500">Top P:</span>
                      <span class="font-medium ml-1"
                        >{selected_run_config.run_config_properties.top_p}</span
                      >
                    </div>
                  {/if}
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
                      >{selected_eval_ids.size} of {evals_with_configs.length} selected</span
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
                Kiln Prompt Optimization will optimize the prompt to maximize
                performance on each of these evaluators.
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
                <div
                  class="bg-base-200 rounded-lg p-4 text-center text-gray-500"
                >
                  No evaluators configured for this task.
                </div>
              {:else}
                <div class="bg-base-200 rounded-lg p-4 space-y-3">
                  {#each evals_with_configs as { eval: evalItem, current_config, has_default_config, has_train_set, train_set_size, model_is_supported, validation_status, validation_message }}
                    {@const spec_id = "legacy"}
                    {@const eval_url = `/specs/${project_id}/${task_id}/${spec_id}/${evalItem.id}`}
                    {@const eval_configs_url = `/specs/${project_id}/${task_id}/${spec_id}/${evalItem.id}/eval_configs`}
                    {@const is_selected = evalItem.id
                      ? selected_eval_ids.has(evalItem.id)
                      : false}
                    <div
                      class={`pl-3 py-2 ${
                        !is_selected ? "opacity-80 text-base-content/70" : ""
                      }`}
                    >
                      <div class="flex items-start justify-between gap-2">
                        <div class="flex-1 min-w-0">
                          <div class="flex items-center gap-2 mb-1">
                            <input
                              type="checkbox"
                              class="checkbox checkbox-sm shrink-0"
                              checked={is_selected}
                              disabled={validation_status === "invalid"}
                              on:change={(e) => {
                                if (evalItem.id) {
                                  const newSet = new Set(selected_eval_ids)
                                  if (e.currentTarget.checked) {
                                    newSet.add(evalItem.id)
                                  } else {
                                    newSet.delete(evalItem.id)
                                  }
                                  selected_eval_ids = newSet
                                }
                              }}
                            />
                            <a
                              href={eval_url}
                              target="_blank"
                              class={`font-medium text-sm link hover:underline min-w-0 truncate ${
                                !is_selected ? "text-base-content/70" : ""
                              }`}
                            >
                              {evalItem.name}
                            </a>
                            {#if validation_status === "checking"}
                              <span
                                class="loading loading-spinner loading-xs shrink-0"
                              ></span>
                            {/if}
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

                          {#if has_train_set && train_set_size !== null}
                            <div class="text-xs text-gray-500">
                              {train_set_size} examples tagged with "{tagFromFilterId(
                                evalItem.train_set_filter_id || "",
                              )}"
                            </div>
                          {/if}

                          {#if validation_message}
                            <div
                              class="text-xs mt-1 {validation_status ===
                              'invalid'
                                ? 'text-error'
                                : 'text-gray-600'}"
                            >
                              {#if !has_default_config}
                                Please set a default config for this evaluator.
                                <a
                                  href={eval_configs_url}
                                  target="_blank"
                                  class="link"
                                >
                                  Set default judge
                                </a>
                              {:else if !model_is_supported}
                                {validation_message}
                                <a
                                  href={eval_configs_url}
                                  target="_blank"
                                  class="link"
                                >
                                  Change default judge
                                </a>
                              {:else if !has_train_set}
                                {validation_message}
                                <button
                                  type="button"
                                  class="link"
                                  on:click={() => {
                                    if (evalItem.id) {
                                      showing_train_set_picker[evalItem.id] =
                                        true
                                      showing_train_set_picker = {
                                        ...showing_train_set_picker,
                                      }
                                    }
                                  }}
                                >
                                  Set train set tag
                                </button>
                              {:else if train_set_size === 0}
                                {validation_message}
                                <a
                                  href="/dataset/{project_id}/{task_id}"
                                  target="_blank"
                                  class="link"
                                >
                                  Tag data with "{tagFromFilterId(
                                    evalItem.train_set_filter_id || "",
                                  )}"
                                </a>
                              {:else}
                                {validation_message}
                              {/if}
                            </div>
                          {/if}

                          {#if !has_train_set && showing_train_set_picker[evalItem.id || ""]}
                            <div class="mt-2 space-y-2">
                              <div class="text-xs text-gray-600">
                                Enter a tag name for the train set:
                              </div>
                              <div class="flex items-center gap-2">
                                <TagDropdown
                                  {project_id}
                                  {task_id}
                                  bind:tag={train_set_tags[evalItem.id || ""]}
                                  on_select={(tag) => {
                                    if (evalItem.id) {
                                      save_train_set_for_eval(evalItem.id, tag)
                                    }
                                  }}
                                  on_escape={() => {
                                    if (evalItem.id) {
                                      train_set_tags[evalItem.id] = ""
                                      showing_train_set_picker[evalItem.id] =
                                        false
                                      train_set_tags = { ...train_set_tags }
                                      showing_train_set_picker = {
                                        ...showing_train_set_picker,
                                      }
                                    }
                                  }}
                                  example_tag_set="task_run"
                                  focus_on_mount={true}
                                />
                                {#if saving_train_set[evalItem.id || ""]}
                                  <span
                                    class="loading loading-spinner loading-xs"
                                  ></span>
                                {/if}
                              </div>
                              {#if train_set_errors[evalItem.id || ""]}
                                <div class="text-error text-xs">
                                  {train_set_errors[evalItem.id || ""]}
                                </div>
                              {/if}
                              <div class="text-xs text-gray-500">
                                After setting the tag, go to the
                                <a
                                  href="/dataset/{project_id}/{task_id}"
                                  target="_blank"
                                  class="link"
                                >
                                  Dataset page
                                </a>
                                to tag your training data with "{train_set_tags[
                                  evalItem.id || ""
                                ] || "(tag name)"}"
                              </div>
                            </div>
                          {/if}
                        </div>
                      </div>
                    </div>
                  {/each}
                </div>
              {/if}

              {#if selected_eval_ids.size === 0}
                <div class="mt-3">
                  <Warning
                    warning_color="gray"
                    warning_icon="info"
                    outline={true}
                    tight={true}
                  >
                    <div class="text-sm text-gray-600">
                      No evaluators selected. Please select at least one
                      evaluator.
                    </div>
                  </Warning>
                </div>
              {:else if has_evals_without_train_set}
                <div class="mt-3">
                  <Warning
                    warning_color="warning"
                    warning_icon="info"
                    outline={true}
                    tight={true}
                  >
                    <div class="text-sm text-gray-600">
                      Some selected evals have no train set and will not be used
                      during optimization.
                    </div>
                  </Warning>
                </div>
              {/if}
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
