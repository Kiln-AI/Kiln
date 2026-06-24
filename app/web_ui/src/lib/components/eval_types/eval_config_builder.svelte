<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import { page } from "$app/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { Eval, Task, EvalConfigType, Spec } from "$lib/types"
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
    checkCodeEvalTrust,
    grantCodeEvalTrust,
    type EvalTaskInput,
    type TestV2EvalResponse,
  } from "$lib/api/v2_eval_api"
  import Dialog from "$lib/ui/dialog.svelte"
  import Collapse from "$lib/ui/collapse.svelte"

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

  $: is_llm_judge = eval_config_type === "llm_judge"
  $: can_submit_v2 = eval_config_type && !is_llm_judge
  $: can_submit_llm =
    is_llm_judge && llm_selected_algo && llm_combined_model_name

  async function run_test() {
    if (!eval_config_type || !v2FormComponent) return

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
        metadata?.requiresTrust
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
</script>

<FormContainer
  submit_visible={!!(can_submit_v2 || can_submit_llm)}
  submit_label="Save"
  on:submit={handle_submit}
  bind:error={create_evaluator_error}
  bind:submitting={create_evaluator_loading}
  warn_before_unload={!complete && !!eval_config_type}
>
  <div class="flex items-center gap-2 pt-4 mb-2">
    {#if metadata}
      <i class="{metadata.icon} text-lg text-primary"></i>
      <span class="text-lg font-bold">{metadata.label}</span>
    {/if}
  </div>

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
            <span class="label-text-alt text-gray-400">Optional JSON array</span
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
                  {test_result.skipped_detail || test_result.skipped_reason}
                </div>
              </div>
            </div>
          {:else if test_result.scores}
            <div class="alert alert-success text-sm">
              <i class="bi bi-check-circle-fill"></i>
              <div>
                <div class="font-medium mb-1">Scores</div>
                <div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
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
