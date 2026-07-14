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
    manualExampleSupport,
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
  import {
    uses_reference_data_llm_judge,
    uses_reference_data_code_eval,
  } from "$lib/utils/eval_types/reference_data_gate"
  import { SHOW_REFERENCE_DATA_UI } from "$lib/utils/eval_types/reference_data_ui"

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
  let llm_judge_prompt: string | undefined = undefined
  let llm_system_prompt: string | undefined = undefined

  // Code eval form binding — tracks code edits reactively for the save gate.
  // Starts undefined so the child's initial value flows up via bind:.
  let code_eval_code: string | undefined = undefined

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

  // Trust, confirm, and test-required modal refs
  let trust_dialog: Dialog
  let confirm_save_dialog: Dialog
  let test_required_dialog: Dialog
  let form_container: FormContainer

  // Pending action after trust grant: "test" or "save"
  let pending_trust_action: "test" | "save" | null = null

  // Reference data candidate keys for dropdown (parsed from test run panel)
  let reference_candidate_keys: string[] = []
  $: reference_candidate_keys = parse_reference_keys(advanced_reference_data)

  function parse_reference_keys(data: string): string[] {
    if (!data.trim()) return []
    try {
      const parsed = JSON.parse(data.trim())
      if (
        parsed === null ||
        typeof parsed !== "object" ||
        Array.isArray(parsed)
      ) {
        return []
      }
      return Object.keys(parsed)
    } catch {
      return []
    }
  }

  // Whether the current config uses reference_data (drives the test-before-save gate).
  // Both llm_judge_prompt and code_eval_code are direct reactive dependencies so
  // Svelte's $: tracking re-evaluates when the user edits either one.
  $: config_uses_reference_data = compute_uses_reference_data(
    eval_config_type,
    llm_judge_prompt,
    code_eval_code,
  )

  function compute_uses_reference_data(
    type: V2EvalType,
    judge_prompt: string | undefined,
    code: string | undefined,
  ): boolean {
    // While reference data is hidden from the UI there's no way to supply it in
    // the Test Judge pane, so the test-before-save gate can never be satisfied.
    // Report "unused" to keep the normal save flow, even if the user hand-wrote
    // a reference_data lookup into their prompt or code.
    if (!SHOW_REFERENCE_DATA_UI) {
      return false
    }
    if (type === "llm_judge") {
      return uses_reference_data_llm_judge(judge_prompt ?? "")
    }
    if (type === "code_eval") {
      return uses_reference_data_code_eval(code ?? "")
    }
    return false
  }

  // Snapshot of prompt/code + reference data at the time of the last passing test.
  // When either changes, the passing test is invalidated.
  let test_passed_snapshot: {
    prompt_or_code: string
    reference_data: string
  } | null = null

  // The effective "test passed" flag: true only when the snapshot matches current state.
  // Uses llm_judge_prompt and code_eval_code as direct reactive dependencies so
  // edits to either invalidate the snapshot immediately.
  $: test_passed_for_current_config = (() => {
    if (!test_passed_snapshot) return false
    const current_prompt_or_code = get_prompt_or_code(
      eval_config_type,
      llm_judge_prompt,
      code_eval_code,
    )
    return (
      test_passed_snapshot.prompt_or_code === current_prompt_or_code &&
      test_passed_snapshot.reference_data === advanced_reference_data
    )
  })()

  function get_prompt_or_code(
    type: V2EvalType,
    judge_prompt: string | undefined,
    code: string | undefined,
  ): string {
    if (type === "llm_judge") return judge_prompt ?? ""
    if (type === "code_eval") return code ?? ""
    return ""
  }

  // Required reference fields surfaced by the active form.
  // Only the deterministic forms (exact_match, contains, set_check) bind
  // this; reset when switching to any other eval type so stale values
  // from a previous form don't leak.
  let required_reference_fields: string[] = []
  $: if (
    eval_config_type !== "exact_match" &&
    eval_config_type !== "contains" &&
    eval_config_type !== "set_check"
  ) {
    required_reference_fields = []
  }

  // Output-source expression surfaced by the deterministic forms (drives the
  // reference-key dropdown and required fields).
  let active_value_expression: string | null = null
  $: manual_example_support = manualExampleSupport(eval_config_type)

  // Unsaved-changes guard: activate after any real form interaction
  let has_typed = false

  function markDirty() {
    has_typed = true
  }

  // LLM-judge model/algo selection uses callback props, not native DOM events,
  // so on:input/on:change on the form wrapper won't catch those changes.
  // Watch the bound values reactively to arm the unsaved-changes guard.
  $: if (llm_combined_model_name || llm_selected_algo) markDirty()

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
        const parsed = JSON.parse(advanced_reference_data.trim())
        if (
          parsed === null ||
          typeof parsed !== "object" ||
          Array.isArray(parsed)
        ) {
          test_error = createKilnError(
            new Error(
              "Reference data must be a JSON object (not null, array, string, or number).",
            ),
          )
          return null
        }
        eval_input.reference_data = parsed
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
    // Clear all prior test state up front so a re-run never leaves a stale
    // result/warning/error on screen — even when an early-return validation
    // path fires before the test runs.
    test_error = null
    test_result = null
    test_has_valid_run = false
    test_shape_warning = null
    test_score_range_warning = null

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

    const controller = new AbortController()
    test_abort_controller = controller

    try {
      test_loading = true

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
            judge_prompt: llm_judge_prompt ?? null,
            system_prompt: llm_system_prompt ?? null,
          },
          eval_input,
          controller.signal,
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
          controller.signal,
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

        if (test_has_valid_run) {
          test_passed_snapshot = {
            prompt_or_code: get_prompt_or_code(
              eval_config_type,
              llm_judge_prompt,
              code_eval_code,
            ),
            reference_data: advanced_reference_data,
          }
        }
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        // User cancelled -- not an error
      } else {
        test_error = createKilnError(e)
      }
    } finally {
      if (test_abort_controller === controller) {
        test_loading = false
        test_abort_controller = null
      }
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
    // Clear any prior error so a re-submit after a fix starts clean.
    create_evaluator_error = null

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

    // Surface form validation errors before prompting to save without testing.
    // A hard error means the config can't be saved at all, so the
    // "Save Without Testing?" confirmation shouldn't appear yet.
    if (!is_llm_judge && v2FormComponent?.validate) {
      const validation_error = v2FormComponent.validate()
      if (validation_error) {
        create_evaluator_loading = false
        create_evaluator_error = createKilnError(new Error(validation_error))
        return
      }
    }

    // When the config uses reference_data, require a passing test with
    // current prompt/code AND reference data before allowing save.
    if (config_uses_reference_data) {
      if (!test_passed_for_current_config) {
        create_evaluator_loading = false
        test_required_dialog.show()
        return
      }
    } else if (!test_has_valid_run) {
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

      // Compute reference_keys from on-page reference data for types that use it.
      const save_reference_keys = config_uses_reference_data
        ? reference_candidate_keys
        : []

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
          judge_prompt: llm_judge_prompt ?? null,
          system_prompt: llm_system_prompt ?? null,
          reference_keys: save_reference_keys,
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
        if (eval_config_type === "code_eval") {
          properties.reference_keys = save_reference_keys
        }
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
          `/specs/${project_id}/${task_id}/${spec_id}/${eval_id}?selected_eval_config=${data.id}`,
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

<!--
  Grid so the intro spans only the form column (row 1, col 1) while the
  Judge Configuration and Test Judge panes sit side-by-side on row 2 at the
  same level. Collapses to a single column below xl.

  FormContainer wraps only the left column so its <form> boundary and
  FormElement validators don't span into the test-run pane.
-->
<div
  class="grid grid-cols-1 gap-y-6 xl:gap-x-16 xl:items-start xl:grid-cols-[minmax(0,1fr)_18rem] 2xl:grid-cols-[minmax(0,1fr)_24rem]"
>
  {#if metadata}
    <div class="min-w-0 xl:col-start-1 xl:row-start-1">
      <EvalTypeIntro evalType={eval_config_type} {metadata} />
    </div>
  {/if}

  <!-- Left: form (inside FormContainer so validation scopes to config fields only) -->
  <div class="min-w-0 xl:col-start-1 xl:row-start-2">
    <FormContainer
      bind:this={form_container}
      submit_visible={false}
      keyboard_submit={false}
      focus_on_mount={false}
      submit_label="Save"
      on:submit={handle_submit}
      bind:error={create_evaluator_error}
      bind:submitting={create_evaluator_loading}
      warn_before_unload={!complete && !!eval_config_type && has_typed}
    >
      <!-- on:input/on:change capture real form interactions for unsaved-changes guard -->
      <div
        class="flex flex-col gap-6"
        on:input={markDirty}
        on:change={markDirty}
      >
        <div>
          <div class="text-xl font-bold">Judge Configuration</div>
        </div>

        {#if is_llm_judge}
          <LlmJudgeForm
            bind:this={llmJudgeFormComponent}
            {task_id}
            {project_id}
            {eval_id}
            bind:model_name={llm_model_name}
            bind:provider_name={llm_provider_name}
            bind:combined_model_name={llm_combined_model_name}
            bind:selected_algo={llm_selected_algo}
            bind:judge_prompt={llm_judge_prompt}
            bind:system_prompt={llm_system_prompt}
          />
        {:else if eval_config_type === "code_eval" && metadata}
          <svelte:component
            this={metadata.createFormComponent}
            bind:this={v2FormComponentRef}
            bind:code_string={code_eval_code}
            output_scores={evaluator?.output_scores}
          />
        {:else if (eval_config_type === "exact_match" || eval_config_type === "contains" || eval_config_type === "set_check") && metadata}
          <svelte:component
            this={metadata.createFormComponent}
            bind:this={v2FormComponentRef}
            {reference_candidate_keys}
            bind:required_reference_fields
            bind:output_value_expression={active_value_expression}
          />
        {:else if eval_config_type === "pattern_match" && metadata}
          <svelte:component
            this={metadata.createFormComponent}
            bind:this={v2FormComponentRef}
            bind:output_value_expression={active_value_expression}
          />
        {:else if eval_config_type === "tool_call_check" && metadata}
          <svelte:component
            this={metadata.createFormComponent}
            bind:this={v2FormComponentRef}
            {project_id}
            {task_id}
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
    </FormContainer>
  </div>

  <!-- Right: test run pane (outside FormContainer — not validated on save) -->
  <div class="min-w-0 xl:col-start-2 xl:row-start-2">
    <EvalTestRunPane
      {project_id}
      {task_id}
      {eval_config_type}
      {runs_loading}
      {runs_error}
      {available_runs}
      selected_run={selected_task_run}
      reference_data={advanced_reference_data}
      {required_reference_fields}
      {test_loading}
      {test_result}
      {test_error}
      {test_shape_warning}
      {test_score_range_warning}
      {test_has_valid_run}
      {is_llm_judge}
      {can_submit_llm}
      manual_example_supported={manual_example_support.supported}
      on:select={(e) => select_task_run(e.detail)}
      on:run={run_test}
      on:cancel={cancel_test}
      on:updateReferenceData={(e) => (advanced_reference_data = e.detail)}
      on:runAgain={run_test}
    />
  </div>
</div>

<Dialog
  bind:this={trust_dialog}
  title="Trust Code and Project?"
  action_buttons={[
    {
      label: "I Trust this Code",
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

<Dialog
  bind:this={test_required_dialog}
  title="Test Required"
  action_buttons={[
    {
      label: "OK",
      isPrimary: true,
      action: () => true,
    },
  ]}
>
  <p class="text-sm text-gray-500">
    You must successfully run your judge once in the <code
      class="bg-base-200 px-1 py-0.5 rounded text-xs font-mono">Test Judge</code
    >
    panel before saving. We must check your
    <code class="bg-base-200 px-1 py-0.5 rounded text-xs font-mono"
      >reference_data</code
    > code works properly.
  </p>
</Dialog>
