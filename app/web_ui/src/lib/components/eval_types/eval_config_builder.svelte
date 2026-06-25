<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import { page } from "$app/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type {
    Eval,
    Task,
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
  import { onMount } from "svelte"
  import EvalTypeIntro from "$lib/components/eval_types/eval_type_intro.svelte"
  import EvalTestRunPane from "$lib/components/eval_types/test_run/eval_test_run_pane.svelte"

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
  let test_score_range_warning: string | null = null
  let test_abort_controller: AbortController | null = null

  // Trust and confirm modal refs
  let trust_dialog: Dialog
  let confirm_save_dialog: Dialog
  let form_container: FormContainer

  // Pending action after trust grant: "test" or "save"
  let pending_trust_action: "test" | "save" | null = null

  $: is_llm_judge = eval_config_type === "llm_judge"
  $: can_submit_v2 = !!eval_config_type && !is_llm_judge
  $: can_submit_llm =
    is_llm_judge && !!llm_selected_algo && !!llm_combined_model_name
  $: can_submit = can_submit_v2 || can_submit_llm

  function handleKeydown(event: KeyboardEvent) {
    if (!can_submit || create_evaluator_loading) return
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault()
      form_container.validate_and_submit()
    }
  }

  onMount(async () => {
    await load_task_runs()
  })

  async function load_task_runs() {
    try {
      runs_loading = true
      runs_error = null
      available_runs = await fetchTaskRuns(project_id, task_id)
      selected_task_run = available_runs[0] ?? null
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
      test_score_range_warning = null
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

        if (result.score_range_errors && result.score_range_errors.length > 0) {
          test_score_range_warning = result.score_range_errors.join("; ")
          test_has_valid_run = false
        }
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
      run_test()
    } else if (action === "save") {
      do_save()
    }
    return true
  }

  async function handle_submit() {
    if (metadata?.requiresTrust) {
      try {
        const trust_response = await checkCodeEvalTrust(project_id)
        if (!trust_response.trusted) {
          pending_trust_action = "save"
          create_evaluator_loading = false
          trust_dialog.show()
          return
        }
      } catch (e) {
        create_evaluator_loading = false
        create_evaluator_error = createKilnError(e)
        return
      }
    }

    if (!test_has_valid_run) {
      create_evaluator_loading = false
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

  function select_task_run(run: TaskRunOutput) {
    selected_task_run = run
    test_result = null
    test_has_valid_run = false
    test_shape_warning = null
    test_score_range_warning = null
    test_error = null
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<FormContainer
  bind:this={form_container}
  submit_visible={false}
  keyboard_submit={false}
  submit_label="Save"
  on:submit={handle_submit}
  bind:error={create_evaluator_error}
  bind:submitting={create_evaluator_loading}
  warn_before_unload={!complete && !!eval_config_type}
>
  <div class="flex flex-col xl:flex-row gap-8 xl:gap-16 xl:items-start">
    <!-- Left: form -->
    <div class="flex-1 min-w-0 flex flex-col gap-6">
      {#if metadata}
        <EvalTypeIntro evalType={eval_config_type} {metadata} />
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

      {#if can_submit}
        <button
          type="button"
          class="btn btn-primary w-full"
          data-testid="column-save-button"
          disabled={create_evaluator_loading}
          on:click={() => form_container.validate_and_submit()}
        >
          {#if create_evaluator_loading}
            <span class="loading loading-spinner loading-md"></span>
          {:else}
            Save
          {/if}
        </button>
      {/if}
    </div>

    <!-- Right: test run pane -->
    <div class="w-72 2xl:w-96 flex-none">
      <EvalTestRunPane
        {runs_loading}
        {runs_error}
        {available_runs}
        selected_run={selected_task_run}
        reference_data={advanced_reference_data}
        {test_loading}
        {test_result}
        {test_error}
        {test_shape_warning}
        {test_score_range_warning}
        {test_has_valid_run}
        {is_llm_judge}
        {can_submit_llm}
        on:select={(e) => select_task_run(e.detail)}
        on:run={run_test}
        on:cancel={cancel_test}
        on:updateReferenceData={(e) => (advanced_reference_data = e.detail)}
        on:runAgain={run_test}
      />
    </div>
  </div>
</FormContainer>

<Dialog
  bind:this={trust_dialog}
  title="Trust Code and Project?"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Run — I Trust This Code",
      isWarning: true,
      asyncAction: grant_trust_and_retry,
    },
  ]}
>
  <div class="flex flex-row items-start gap-4">
    <!-- exclaim icon from warning.svelte (keep in sync) -->
    <svg
      class="w-10 h-10 text-warning flex-none"
      fill="currentColor"
      viewBox="0 0 256 256"
      xmlns="http://www.w3.org/2000/svg"
      data-testid="trust-warning-icon"
    >
      <path
        d="M128,20.00012a108,108,0,1,0,108,108A108.12217,108.12217,0,0,0,128,20.00012Zm0,192a84,84,0,1,1,84-84A84.0953,84.0953,0,0,1,128,212.00012Zm-12-80v-52a12,12,0,1,1,24,0v52a12,12,0,1,1-24,0Zm28,40a16,16,0,1,1-16-16A16.018,16.018,0,0,1,144,172.00012Z"
      />
    </svg>
    <div class="flex flex-col gap-2 text-sm text-left">
      <p>
        This project wants to run Python code on your machine. Only proceed if
        you trust the eval code and this project.
      </p>
      <p class="font-bold">Never paste code from a stranger or the internet.</p>
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
  <p class="text-sm text-gray-500">
    You haven't tested this judge yet. Running a quick test helps catch issues
    before saving. Are you sure you want to save without testing?
  </p>
</Dialog>
