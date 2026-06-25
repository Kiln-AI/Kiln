<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import { page } from "$app/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type {
    Eval,
    Task,
    TaskRun,
    EvalConfigType,
    Spec,
    TaskRunOutput,
  } from "$lib/types"
  import type { components } from "$lib/api_schema"
  import { goto } from "$app/navigation"
  import posthog from "posthog-js"
  import { set_current_eval_config } from "$lib/stores/evals_store"
  import LlmJudgeForm from "$lib/components/eval_types/llm_judge_form.svelte"
  import {
    getV2EvalTypeMetadata,
    type V2EvalType,
    type EvalTypeFormApi,
  } from "$lib/utils/eval_types/registry"
  import {
    createEvalConfig,
    createLlmJudgeConfig,
    testV2Eval,
    testV2EvalLlmJudge,
    fetchTaskRuns,
    checkCodeEvalTrust,
    grantCodeEvalTrust,
    type EvalTaskInput,
    type TestV2EvalResponse,
  } from "$lib/api/v2_eval_api"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
  import Dialog from "$lib/ui/dialog.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import TaskRunPicker from "$lib/utils/task_run_picker.svelte"
  import { onMount } from "svelte"
  import { formatExpandedContent } from "$lib/utils/format_expanded_content"
  import EvalTypeIntro from "$lib/components/eval_types/eval_type_intro.svelte"

  export let eval_config_type: V2EvalType
  export let evaluator: Eval
  export let task: Task
  export let spec: Spec | null
  export let project_id: string
  export let task_id: string
  export let eval_id: string
  export let spec_id: string

  $: metadata = getV2EvalTypeMetadata(eval_config_type)

  // LLM judge form bindings
  let llm_model_name: string | undefined = undefined
  let llm_provider_name: string | undefined = undefined
  let llm_combined_model_name: string | undefined = undefined
  let llm_selected_algo: EvalConfigType | undefined = undefined

  // Form component references -- bind:this on svelte:component yields a
  // generic component instance, so we keep a loose ref and cast it.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let v2FormComponentRef: any
  $: v2FormComponent = v2FormComponentRef as EvalTypeFormApi | undefined
  let llmJudgeFormComponent: LlmJudgeForm

  // Save state
  let create_evaluator_error: KilnError | null = null
  let create_evaluator_loading = false
  let complete = false

  // Test-run panel state
  let available_runs: TaskRunOutput[] = []
  let runs_loading = true
  let runs_error: KilnError | null = null
  let selected_task_run: TaskRunOutput | null = null
  let advanced_reference_data = ""
  let test_loading = false
  let test_error: KilnError | null = null
  let test_result: TestV2EvalResponse | null = null
  let test_has_valid_run = false
  let test_shape_warning: string | null = null
  let test_abort_controller: AbortController | null = null

  // Trust and confirm modal refs
  let trust_dialog: Dialog
  let confirm_save_dialog: Dialog

  // Pending action after trust grant: "test" or "save"
  let pending_trust_action: "test" | "save" | null = null

  $: is_llm_judge = eval_config_type === "llm_judge"
  $: can_submit_v2 = !!eval_config_type && !is_llm_judge
  $: can_submit_llm =
    is_llm_judge && llm_selected_algo && llm_combined_model_name
  $: can_submit = can_submit_v2 || can_submit_llm
  $: has_runs = available_runs.length > 0

  onMount(async () => {
    await load_task_runs()
  })

  async function load_task_runs() {
    try {
      runs_loading = true
      runs_error = null
      available_runs = await fetchTaskRuns(project_id, task_id)
    } catch (e) {
      runs_error = createKilnError(e)
    } finally {
      runs_loading = false
    }
  }

  function build_eval_input(): EvalTaskInput | null {
    if (!selected_task_run) return null

    const eval_input: EvalTaskInput = {
      final_message: selected_task_run.output?.output ?? "",
    }

    if (selected_task_run.input) {
      eval_input.task_input = selected_task_run.input
    }

    if (selected_task_run.trace) {
      eval_input.trace = selected_task_run.trace as {
        [key: string]: unknown
      }[]
    }

    if (advanced_reference_data.trim()) {
      try {
        eval_input.reference_data = JSON.parse(advanced_reference_data.trim())
      } catch {
        test_error = createKilnError(
          new Error("Reference data must be valid JSON (object)."),
        )
        return null
      }
    }

    return eval_input
  }

  function validate_result_shape(scores: Record<string, number> | undefined): {
    valid: boolean
    message: string | null
  } {
    if (!scores || !evaluator?.output_scores?.length) {
      return { valid: true, message: null }
    }

    const expected_keys = evaluator.output_scores.map((s) =>
      string_to_json_key(s.name),
    )
    const returned_keys = Object.keys(scores)
    const missing = expected_keys.filter((k) => !returned_keys.includes(k))

    if (missing.length > 0) {
      return {
        valid: false,
        message: `Missing expected scores: ${missing.join(", ")}. The eval returned: ${returned_keys.join(", ") || "(none)"}`,
      }
    }
    return { valid: true, message: null }
  }

  async function run_test() {
    const eval_input = build_eval_input()
    if (!eval_input) return

    if (is_llm_judge) {
      if (!llm_model_name || !llm_provider_name || !llm_selected_algo) {
        test_error = createKilnError(
          new Error("Please select a model and algorithm first."),
        )
        return
      }
    } else {
      if (!v2FormComponent) return
      if (v2FormComponent.validate) {
        const validation_error = v2FormComponent.validate()
        if (validation_error) {
          test_error = createKilnError(new Error(validation_error))
          return
        }
      }
    }

    try {
      test_loading = true
      test_error = null
      test_result = null
      test_has_valid_run = false
      test_shape_warning = null
      test_abort_controller = new AbortController()

      let result: TestV2EvalResponse

      if (is_llm_judge) {
        const g_eval = llm_selected_algo === "g_eval"
        result = await testV2EvalLlmJudge(
          project_id,
          task_id,
          eval_id,
          {
            model_name: llm_model_name!,
            provider:
              llm_provider_name! as components["schemas"]["ModelProviderName"],
            g_eval,
          },
          eval_input,
          test_abort_controller.signal,
        )
      } else {
        const properties = v2FormComponent!.getProperties()
        result = await testV2Eval(
          project_id,
          task_id,
          eval_id,
          {
            properties,
            eval_input,
          },
          test_abort_controller.signal,
        )
      }

      if (
        result.skipped_reason === "code_eval_not_trusted" &&
        metadata?.requiresTrust
      ) {
        pending_trust_action = "test"
        trust_dialog.show()
        test_loading = false
        return
      }

      test_result = result

      if (result.scores && !result.skipped_reason) {
        const shape = validate_result_shape(result.scores)
        test_has_valid_run = shape.valid
        test_shape_warning = shape.message
      }
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
    if (metadata?.requiresTrust) {
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

    if (!test_has_valid_run) {
      confirm_save_dialog.show()
      return
    }

    await do_save()
  }

  async function do_save() {
    try {
      create_evaluator_loading = true
      create_evaluator_error = null

      let data: components["schemas"]["EvalConfig"]

      if (is_llm_judge) {
        if (!llm_model_name || !llm_provider_name || !llm_selected_algo) {
          throw new Error("No model or algorithm selected")
        }
        const g_eval = llm_selected_algo === "g_eval"
        data = await createLlmJudgeConfig(project_id, task_id, eval_id, {
          model_name: llm_model_name,
          provider:
            llm_provider_name as components["schemas"]["ModelProviderName"],
          g_eval,
        })
      } else if (eval_config_type && v2FormComponent) {
        if (v2FormComponent.validate) {
          const validation_error = v2FormComponent.validate()
          if (validation_error) {
            throw new Error(validation_error)
          }
        }
        const properties = v2FormComponent.getProperties() as Record<
          string,
          unknown
        >
        data = await createEvalConfig(project_id, task_id, eval_id, {
          type: "v2",
          properties,
          model_name: null,
          provider: null,
        })
      } else {
        throw new Error("No eval type selected")
      }

      posthog.capture("create_eval_config", {
        config_type: "v2",
        v2_type: eval_config_type,
        ...(is_llm_judge
          ? { model_name: llm_model_name, provider_name: llm_provider_name }
          : {}),
      })

      const save_as_default = $page.url.searchParams.get("save_as_default")
      if (data.id && save_as_default === "true") {
        try {
          await set_current_eval_config(project_id, task_id, eval_id, data.id)
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

  function select_task_run(run: TaskRunOutput | TaskRun) {
    selected_task_run = run as TaskRunOutput
    test_result = null
    test_has_valid_run = false
    test_shape_warning = null
    test_error = null
  }

  function clear_selection() {
    selected_task_run = null
    test_result = null
    test_has_valid_run = false
    test_shape_warning = null
    test_error = null
  }
</script>

<FormContainer
  submit_visible={!!can_submit}
  submit_label="Save"
  on:submit={handle_submit}
  bind:error={create_evaluator_error}
  bind:submitting={create_evaluator_loading}
  warn_before_unload={!complete && !!eval_config_type}
>
  <div class="flex flex-col xl:flex-row gap-8 xl:gap-16">
    <!-- Left: form -->
    <div class="flex-1 min-w-0">
      {#if metadata}
        <EvalTypeIntro {metadata} />
      {/if}

      {#if is_llm_judge}
        <LlmJudgeForm
          bind:this={llmJudgeFormComponent}
          {task_id}
          bind:model_name={llm_model_name}
          bind:provider_name={llm_provider_name}
          bind:combined_model_name={llm_combined_model_name}
          bind:selected_algo={llm_selected_algo}
        />
      {:else if eval_config_type === "code_eval" && metadata}
        <svelte:component
          this={metadata.createFormComponent}
          bind:this={v2FormComponentRef}
          output_scores={evaluator?.output_scores}
        />
      {:else if metadata}
        <svelte:component
          this={metadata.createFormComponent}
          bind:this={v2FormComponentRef}
        />
      {/if}
    </div>

    <!-- Right: test run pane -->
    <div class="w-72 2xl:w-96 flex-none">
      <div class="flex flex-col gap-3">
        <div class="text-xl font-bold">Test Run</div>
        <p class="text-xs text-gray-500">
          Pick a recent task output to test your evaluator before saving.
        </p>

        {#if runs_loading}
          <div class="flex items-center gap-2 text-sm text-gray-400 py-4">
            <span class="loading loading-spinner loading-xs"></span>
            Loading task runs...
          </div>
        {:else if runs_error}
          <div class="alert alert-error text-sm">
            <i class="bi bi-exclamation-triangle-fill"></i>
            <span>{runs_error.getMessage()}</span>
          </div>
        {:else if !has_runs}
          <div class="flex flex-col items-center gap-2 py-6 text-center">
            <i class="bi bi-inbox text-2xl text-gray-300"></i>
            <div class="text-sm text-gray-500">
              No task runs found. Run your task to generate sample inputs for
              testing.
            </div>
          </div>
        {:else if !selected_task_run}
          <TaskRunPicker
            {available_runs}
            on:select={(e) => select_task_run(e.detail)}
          />
        {:else}
          {@const input_text = selected_task_run.input ?? ""}
          {@const output_text = selected_task_run.output?.output ?? ""}
          {@const input_content = formatExpandedContent(input_text)}
          {@const output_content = formatExpandedContent(output_text)}
          <div class="rounded border bg-base-200 p-3 flex flex-col gap-2">
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-gray-500">Selected Run</span
              >
              <button
                type="button"
                class="btn btn-xs btn-ghost"
                on:click={clear_selection}
              >
                Change
              </button>
            </div>
            <div class="text-xs">
              <span class="font-medium">Input:</span>
              <span class="text-gray-600 break-words"
                >{@html input_content.isJson
                  ? input_content.value
                  : ""}{input_content.isJson
                  ? ""
                  : input_content.value.length > 100
                    ? input_content.value.substring(0, 100) + "..."
                    : input_content.value}</span
              >
            </div>
            <div class="text-xs">
              <span class="font-medium">Output:</span>
              <span class="text-gray-600 break-words"
                >{@html output_content.isJson
                  ? output_content.value
                  : ""}{output_content.isJson
                  ? ""
                  : output_content.value.length > 100
                    ? output_content.value.substring(0, 100) + "..."
                    : output_content.value}</span
              >
            </div>
          </div>

          <Collapse title="Advanced" open={false}>
            <div class="form-control pt-2">
              <label for="advanced_reference_data" class="label">
                <span class="label-text text-xs">Reference Data</span>
                <span class="label-text-alt text-gray-400 text-xs"
                  >Optional JSON object</span
                >
              </label>
              <textarea
                id="advanced_reference_data"
                class="textarea textarea-bordered w-full font-mono text-xs"
                rows="3"
                placeholder={'{"expected_answer": "..."}'}
                bind:value={advanced_reference_data}
              ></textarea>
            </div>
          </Collapse>

          <div class="flex items-center gap-2">
            <button
              type="button"
              class="btn btn-primary btn-sm"
              disabled={test_loading || (is_llm_judge && !can_submit_llm)}
              on:click={run_test}
            >
              {#if test_loading}
                <span class="loading loading-spinner loading-xs"></span>
                Running...
              {:else}
                <i class="bi bi-play-fill"></i>
                Run Test
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

          {#if test_shape_warning}
            <div class="alert alert-warning text-sm">
              <i class="bi bi-exclamation-triangle-fill"></i>
              <div>
                <div class="font-medium">Score Shape Mismatch</div>
                <div class="text-xs">{test_shape_warning}</div>
              </div>
            </div>
          {/if}

          {#if test_result}
            {#if test_result.skipped_reason}
              <div class="alert alert-warning text-sm">
                <i class="bi bi-skip-forward-fill"></i>
                <div>
                  <div class="font-medium">Skipped</div>
                  <div>
                    {test_result.skipped_detail || test_result.skipped_reason}
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
        {/if}
      </div>
    </div>
  </div>
</FormContainer>

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
