<script lang="ts">
  import AppPage from "../../../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, SvelteComponent, tick } from "svelte"
  import type { Eval, Task, EvalConfigType, Spec } from "$lib/types"
  import type { components } from "$lib/api_schema"
  import { load_task, load_available_models } from "$lib/stores"
  import { goto } from "$app/navigation"
  import posthog from "posthog-js"
  import { set_current_eval_config } from "$lib/stores/evals_store"
  import { agentInfo } from "$lib/agent"
  import LlmJudgeForm from "$lib/components/eval_types/llm_judge_form.svelte"
  import {
    ALL_V2_EVAL_TYPES,
    getV2EvalTypeMetadata,
    type V2EvalType,
    type EvalTypeFormApi,
  } from "$lib/utils/eval_types/registry"
  import {
    createEvalConfig,
    testV2Eval,
    checkCodeEvalTrust,
    grantCodeEvalTrust,
    type EvalTaskInput,
    type TestV2EvalResponse,
  } from "$lib/api/v2_eval_api"
  import Dialog from "$lib/ui/dialog.svelte"
  import Collapse from "$lib/ui/collapse.svelte"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: eval_id = $page.params.eval_id!
  $: spec_id = $page.params.spec_id!
  $: agentInfo.set({
    name: "Create Eval Config",
    description: `Create a new eval configuration for eval ID ${eval_id}, spec ID ${spec_id} in project ID ${project_id}, task ID ${task_id}. Eval name: ${evaluator?.name ?? "[loading]"}.`,
  })

  let spec: Spec | null = null
  let spec_loading = true
  let spec_error: KilnError | null = null

  let evaluator: Eval | undefined = undefined
  let task: Task | null = null

  let loading_eval = true
  let loading_eval_error: KilnError | undefined = undefined
  let loading_task = true
  let loading_task_error: KilnError | undefined = undefined
  $: loading = loading_eval || loading_task || spec_loading
  $: loading_error = loading_eval_error || loading_task_error || spec_error

  onMount(async () => {
    await tick()

    const config_type_param = $page.url.searchParams.get("config_type")
    if (
      config_type_param === "g_eval" ||
      config_type_param === "llm_as_judge"
    ) {
      selected_v2_type = "llm_judge"
    } else if (ALL_V2_EVAL_TYPES.includes(config_type_param as V2EvalType)) {
      selected_v2_type = config_type_param as V2EvalType
    }

    await load_eval()
    await get_spec()
    await load_task_local()
    await load_available_models()
  })

  async function get_spec() {
    if (spec_id === "legacy") {
      spec_loading = false
      return
    }
    try {
      spec_loading = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: {
              project_id: project_id,
              task_id: task_id,
              spec_id: spec_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      spec = data
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      spec_loading = false
    }
  }

  async function load_task_local() {
    try {
      loading_task = true
      if (!evaluator) {
        loading_task_error = createKilnError(
          new Error("Evaluator not loaded, can not load task"),
        )
        return
      }

      task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Task not found")
      }
    } catch (e) {
      loading_task_error = createKilnError(e)
    } finally {
      loading_task = false
    }
  }

  async function load_eval() {
    try {
      loading_eval = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
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
      if (error) {
        throw error
      }
      evaluator = data
    } catch (e) {
      loading_eval_error = createKilnError(e)
    } finally {
      loading_eval = false
    }
  }

  // V2 eval type picker
  let selected_v2_type: V2EvalType | null = null
  $: selected_metadata = selected_v2_type
    ? getV2EvalTypeMetadata(selected_v2_type)
    : null

  function select_v2_type(type: V2EvalType) {
    selected_v2_type = type
  }

  function go_back_to_type_picker() {
    selected_v2_type = null
  }

  // LLM judge form bindings
  let llm_model_name: string | undefined = undefined
  let llm_provider_name: string | undefined = undefined
  let llm_combined_model_name: string | undefined = undefined
  let llm_selected_algo: EvalConfigType | undefined = undefined

  // Form component references — Svelte 4 bind:this on <svelte:component> yields
  // a SvelteComponent instance, which doesn't encode the imperative API in its
  // type. We bind to SvelteComponent and derive a typed accessor.
  let v2FormComponentRef: SvelteComponent | undefined
  $: v2FormComponent = v2FormComponentRef as unknown as
    | EvalTypeFormApi
    | undefined
  let llmJudgeFormComponent: LlmJudgeForm

  // Save state
  let create_evaluator_error: KilnError | null = null
  let create_evaluator_loading = false
  let complete = false

  // Test-run panel state
  let test_final_message = ""
  let test_trace = ""
  let test_reference_data = ""
  let test_task_input = ""
  let test_loading = false
  let test_error: KilnError | null = null
  let test_result: TestV2EvalResponse | null = null
  let test_has_run = false
  let test_abort_controller: AbortController | null = null

  // Trust and confirm modal refs
  let trust_dialog: Dialog
  let confirm_save_dialog: Dialog

  // Pending action after trust grant: "test" or "save"
  let pending_trust_action: "test" | "save" | null = null

  $: is_llm_judge = selected_v2_type === "llm_judge"
  $: can_submit_v2 = selected_v2_type && !is_llm_judge
  $: can_submit_llm =
    is_llm_judge && llm_selected_algo && llm_combined_model_name

  async function run_test() {
    if (!selected_v2_type || !v2FormComponent) return

    if (v2FormComponent.validate) {
      const validation_error = v2FormComponent.validate()
      if (validation_error) {
        test_error = createKilnError(new Error(validation_error))
        return
      }
    }

    const properties = v2FormComponent.getProperties()

    const eval_input: EvalTaskInput = {
      final_message: test_final_message,
    }
    if (test_trace.trim()) {
      try {
        eval_input.trace = JSON.parse(test_trace.trim())
      } catch {
        test_error = createKilnError(
          new Error("Trace must be valid JSON (array of objects)."),
        )
        return
      }
    }
    if (test_reference_data.trim()) {
      try {
        eval_input.reference_data = JSON.parse(test_reference_data.trim())
      } catch {
        test_error = createKilnError(
          new Error("Reference data must be valid JSON (object)."),
        )
        return
      }
    }
    if (test_task_input.trim()) {
      eval_input.task_input = test_task_input.trim()
    }

    try {
      test_loading = true
      test_error = null
      test_result = null
      test_abort_controller = new AbortController()

      const result = await testV2Eval(
        project_id,
        task_id,
        eval_id,
        {
          properties,
          eval_input,
        },
        test_abort_controller.signal,
      )

      if (
        result.skipped_reason === "code_eval_not_trusted" &&
        selected_metadata?.requiresTrust
      ) {
        pending_trust_action = "test"
        trust_dialog.show()
        test_loading = false
        return
      }

      test_result = result
      test_has_run = true
    } catch (e) {
      test_error = createKilnError(e)
    } finally {
      test_loading = false
      test_abort_controller = null
    }
  }

  function cancel_test() {
    if (test_abort_controller) {
      test_abort_controller.abort()
      test_abort_controller = null
    }
    test_loading = false
  }

  async function grant_trust_and_retry(): Promise<boolean> {
    try {
      await grantCodeEvalTrust(project_id)
    } catch (e) {
      test_error = createKilnError(e)
      return false
    }
    const action = pending_trust_action
    pending_trust_action = null
    if (action === "test") {
      await run_test()
    } else if (action === "save") {
      await do_save()
    }
    return true
  }

  async function handle_submit() {
    // Trust gate: if type requires trust, check before saving
    if (selected_metadata?.requiresTrust) {
      try {
        const trust_response = await checkCodeEvalTrust(project_id)
        if (!trust_response.trusted) {
          pending_trust_action = "save"
          trust_dialog.show()
          return
        }
      } catch (e) {
        create_evaluator_error = createKilnError(e)
        return
      }
    }

    // Save-without-testing gate: if V2 type and hasn't run test, confirm
    if (can_submit_v2 && !test_has_run) {
      confirm_save_dialog.show()
      return
    }

    await do_save()
  }

  async function do_save() {
    try {
      create_evaluator_loading = true
      create_evaluator_error = null

      let config_type: EvalConfigType
      let properties: Record<string, unknown>
      let model_name: string | undefined
      let provider: string | undefined

      if (is_llm_judge && llmJudgeFormComponent) {
        config_type = llmJudgeFormComponent.getConfigType() ?? "llm_as_judge"
        properties = llmJudgeFormComponent.getProperties()
        model_name = llm_model_name
        provider = llm_provider_name
        if (!model_name || !provider) {
          throw new Error("No model selected")
        }
      } else if (selected_v2_type && v2FormComponent) {
        if (v2FormComponent.validate) {
          const validation_error = v2FormComponent.validate()
          if (validation_error) {
            throw new Error(validation_error)
          }
        }
        config_type = "v2"
        properties = v2FormComponent.getProperties() as Record<string, unknown>
      } else {
        throw new Error("No eval type selected")
      }

      const data = await createEvalConfig(project_id, task_id, eval_id, {
        type: config_type,
        properties,
        model_name: model_name ?? null,
        provider:
          (provider as components["schemas"]["ModelProviderName"]) ?? null,
      })

      posthog.capture("create_eval_config", {
        config_type,
        v2_type: selected_v2_type,
        model_name: model_name,
        provider_name: provider,
      })

      const save_as_default = $page.url.searchParams.get("save_as_default")
      if (data.id && save_as_default === "true") {
        try {
          evaluator = await set_current_eval_config(
            project_id,
            task_id,
            eval_id,
            data.id,
          )
        } catch (e) {
          console.error("Failed to set as default:", e)
        }
      }

      complete = true
      const next_page = $page.url.searchParams.get("next_page")
      if (next_page === "eval_configs") {
        goto(
          `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}/eval_configs`,
        )
      } else if (next_page === "compare_run_configs") {
        goto(
          `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}/compare_run_configs`,
        )
      } else {
        goto(
          `/specs/${project_id}/${task_id}/${spec_id}/eval?selected_eval_config=${data.id}`,
        )
      }
    } catch (e) {
      create_evaluator_error = createKilnError(e)
    } finally {
      create_evaluator_loading = false
    }
  }

  type Breadcrumb = {
    label: string
    href: string
  }

  $: breadcrumbs = (() => {
    const next_page = $page.url.searchParams.get("next_page")
    const crumbs: Breadcrumb[] = [
      {
        label: "Evals",
        href: `/specs/${project_id}/${task_id}`,
      },
      {
        label: spec?.name || "Eval",
        href: `/specs/${project_id}/${task_id}/${spec_id}`,
      },
      {
        label: "Eval",
        href: `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}`,
      },
    ]

    if (next_page === "eval_configs") {
      crumbs.push({
        label: "Compare Judges",
        href: `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}/eval_configs`,
      })
    } else if (next_page === "compare_run_configs") {
      crumbs.push({
        label: "Compare Run Configurations",
        href: `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}/compare_run_configs`,
      })
    }

    return crumbs
  })()
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Add a Judge"
    subtitle="A judge evaluates task outputs with a model, evaluation prompt, and algorithm."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/evaluations#finding-the-ideal-eval-method"
    {breadcrumbs}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task Information</div>
        <div class="text-error text-sm">
          {loading_error?.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else if !selected_v2_type}
      <div class="pt-6">
        <div class="text-xl font-bold mb-2">Select Eval Type</div>
        <div class="text-xs text-gray-500 mb-6">
          Choose the type of evaluator to create. Different types are suited for
          different evaluation needs.
        </div>

        <div class="flex flex-wrap gap-4">
          {#each ALL_V2_EVAL_TYPES as evalType}
            {@const metadata = getV2EvalTypeMetadata(evalType)}
            <button
              class="card card-bordered border-base-300 shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 w-[220px] p-5 flex flex-col items-center text-center group cursor-pointer"
              on:click={() => select_v2_type(evalType)}
            >
              <div class="flex flex-col gap-3 items-center">
                <i
                  class="{metadata.icon} text-2xl text-primary group-hover:scale-110 transition-transform"
                ></i>
                <div class="flex flex-col gap-1">
                  <div class="font-medium text-sm leading-tight">
                    {metadata.label}
                  </div>
                  <div class="text-xs text-gray-500">
                    {metadata.description}
                  </div>
                </div>
              </div>
            </button>
          {/each}
        </div>
      </div>
    {:else}
      <FormContainer
        submit_visible={!!(can_submit_v2 || can_submit_llm)}
        submit_label="Create Judge"
        on:submit={handle_submit}
        bind:error={create_evaluator_error}
        bind:submitting={create_evaluator_loading}
        warn_before_unload={!complete && !!selected_v2_type}
      >
        <div class="flex items-center gap-2 pt-4 mb-2">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            on:click={go_back_to_type_picker}
          >
            <i class="bi bi-arrow-left"></i>
            Back
          </button>
          {#if selected_metadata}
            <div class="flex items-center gap-2">
              <i class="{selected_metadata.icon} text-lg text-primary"></i>
              <span class="text-lg font-bold">{selected_metadata.label}</span>
            </div>
          {/if}
        </div>

        {#if is_llm_judge && evaluator && task}
          <LlmJudgeForm
            bind:this={llmJudgeFormComponent}
            {evaluator}
            {task}
            {spec}
            {task_id}
            bind:model_name={llm_model_name}
            bind:provider_name={llm_provider_name}
            bind:combined_model_name={llm_combined_model_name}
            bind:selected_algo={llm_selected_algo}
          />
        {:else if selected_v2_type === "code_eval" && selected_metadata}
          <svelte:component
            this={selected_metadata.createFormComponent}
            bind:this={v2FormComponentRef}
            output_scores={evaluator?.output_scores}
          />
        {:else if selected_metadata}
          <svelte:component
            this={selected_metadata.createFormComponent}
            bind:this={v2FormComponentRef}
          />
        {/if}

        {#if can_submit_v2}
          <div class="divider"></div>
          <Collapse
            title="Test Your Judge"
            description="Run a quick test to verify your evaluator works as expected before saving."
            open={false}
          >
            <div class="flex flex-col gap-4 pt-2">
              <div class="form-control">
                <label for="test_final_message" class="label">
                  <span class="label-text font-medium"
                    >Final Message <span class="text-error">*</span></span
                  >
                </label>
                <textarea
                  id="test_final_message"
                  class="textarea textarea-bordered w-full"
                  rows="3"
                  placeholder="The model's final output to evaluate..."
                  bind:value={test_final_message}
                ></textarea>
              </div>

              <div class="form-control">
                <label for="test_task_input" class="label">
                  <span class="label-text">Task Input</span>
                  <span class="label-text-alt text-gray-400">Optional</span>
                </label>
                <input
                  id="test_task_input"
                  type="text"
                  class="input input-bordered w-full"
                  placeholder="The original task input..."
                  bind:value={test_task_input}
                />
              </div>

              <div class="form-control">
                <label for="test_trace" class="label">
                  <span class="label-text">Trace</span>
                  <span class="label-text-alt text-gray-400"
                    >Optional JSON array</span
                  >
                </label>
                <textarea
                  id="test_trace"
                  class="textarea textarea-bordered w-full font-mono text-sm"
                  rows="2"
                  placeholder={'[{"role": "user", "content": "..."}, ...]'}
                  bind:value={test_trace}
                ></textarea>
              </div>

              <div class="form-control">
                <label for="test_reference_data" class="label">
                  <span class="label-text">Reference Data</span>
                  <span class="label-text-alt text-gray-400"
                    >Optional JSON object</span
                  >
                </label>
                <textarea
                  id="test_reference_data"
                  class="textarea textarea-bordered w-full font-mono text-sm"
                  rows="2"
                  placeholder={'{"expected_answer": "..."}'}
                  bind:value={test_reference_data}
                ></textarea>
              </div>

              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="btn btn-primary btn-sm"
                  disabled={!test_final_message.trim() || test_loading}
                  on:click={run_test}
                >
                  {#if test_loading}
                    <span class="loading loading-spinner loading-xs"></span>
                    Running...
                  {:else}
                    <i class="bi bi-play-fill"></i>
                    Try It
                  {/if}
                </button>
                {#if test_loading}
                  <button
                    type="button"
                    class="btn btn-ghost btn-sm"
                    on:click={cancel_test}
                  >
                    Cancel
                  </button>
                {/if}
              </div>

              {#if test_error}
                <div class="alert alert-error text-sm">
                  <i class="bi bi-exclamation-triangle-fill"></i>
                  <span>{test_error.getMessage()}</span>
                </div>
              {/if}

              {#if test_result}
                {#if test_result.skipped_reason}
                  <div class="alert alert-warning text-sm">
                    <i class="bi bi-skip-forward-fill"></i>
                    <div>
                      <div class="font-medium">Skipped</div>
                      <div>
                        {test_result.skipped_detail ||
                          test_result.skipped_reason}
                      </div>
                    </div>
                  </div>
                {:else if test_result.scores}
                  <div class="alert alert-success text-sm">
                    <i class="bi bi-check-circle-fill"></i>
                    <div>
                      <div class="font-medium mb-1">Scores</div>
                      <div
                        class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs"
                      >
                        {#each Object.entries(test_result.scores) as [name, value]}
                          <span class="font-mono font-medium">{name}</span>
                          <span>{value}</span>
                        {/each}
                      </div>
                    </div>
                  </div>
                {/if}
              {/if}
            </div>
          </Collapse>
        {/if}
      </FormContainer>
    {/if}
  </AppPage>
</div>

<Dialog
  bind:this={trust_dialog}
  title="Allow Code Execution"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "I Understand, Allow Execution",
      isWarning: true,
      asyncAction: grant_trust_and_retry,
    },
  ]}
>
  <div class="flex flex-col gap-3">
    <div class="alert alert-warning text-sm">
      <i class="bi bi-exclamation-triangle-fill"></i>
      <span
        >This eval runs Python code on your machine. Only proceed if you trust
        eval code inside this project.</span
      >
    </div>
  </div>
</Dialog>

<Dialog
  bind:this={confirm_save_dialog}
  title="Save Without Testing?"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Save Anyway",
      isError: true,
      asyncAction: async () => {
        await do_save()
        return true
      },
    },
  ]}
>
  <p class="text-sm text-gray-600">
    You haven't tested this judge yet. Running a quick test helps catch issues
    before saving. Are you sure you want to save without testing?
  </p>
</Dialog>
