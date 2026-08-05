<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import JudgeConfigFields from "$lib/components/eval_types/judge_config_fields.svelte"
  import EvalTypeIntro from "$lib/components/eval_types/eval_type_intro.svelte"
  import EvalTestRunPane from "$lib/components/eval_types/test_run/eval_test_run_pane.svelte"
  import TrustCodeDialog from "$lib/components/eval_types/trust_code_dialog.svelte"
  import {
    getV2EvalTypeMetadata,
    manualExampleSupport,
  } from "$lib/utils/eval_types/registry"
  import type { V2EvalType } from "$lib/utils/eval_types/registry"
  import type { V2EvalConfigProperties } from "$lib/api/v2_eval_api"
  import {
    fetchTaskRuns,
    testV2EvalDraft,
    addCodeTrust,
    type EvalTaskInput,
    type TestV2EvalResponse,
  } from "$lib/api/v2_eval_api"
  import { filename_string_short_validator } from "$lib/utils/input_validators"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"
  import type { EvalOutputScore, Priority, TaskRunOutput } from "$lib/types"

  /**
   * Create form for an eval whose judge doesn't read a written rubric.
   *
   * No spec is created for these evals: the template's fields exist to flesh
   * out an LLM judge's prompt, which a deterministic judge never reads, so the
   * form is just the eval's name and the judge's own configuration.
   */
  export let name: string
  export let judge_type: V2EvalType
  export let project_id: string
  export let task_id: string
  export let priority: Priority = 1
  export let evaluate_full_trace: boolean
  export let full_trace_disabled: boolean
  export let error: KilnError | null
  export let submitting: boolean
  export let warn_before_unload: boolean

  let judge_fields: JudgeConfigFields

  const dispatch = createEventDispatcher<{ save: void }>()

  $: judge_metadata = getV2EvalTypeMetadata(judge_type)

  // The eval will be created with a single pass/fail score named after the
  // eval. The judge forms need that shape up front: the code judge shows the
  // score key it implies, live as the name is typed. Its starter code uses a
  // static "score_name_placeholder" key rather than chasing this field.
  // While the name field is invalid, no scores are passed down: a key derived
  // from a rejected name would be wrong, so the score-key note hides instead.
  let name_error: string | null = null
  $: output_scores = (
    name_error ? [] : [{ name, type: "pass_fail" }]
  ) as EvalOutputScore[]

  // The form arrives pre-filled (autofilled name, judge defaults), so "has
  // unsaved changes" has to mean the user actually touched something --
  // otherwise simply opening the page and pressing back would warn.
  const initial_name = name
  let has_typed = false

  function markDirty() {
    has_typed = true
  }

  // The code judge's editor doesn't emit bubbling DOM input events, so compare its
  // value against the default it seeds itself with instead of relying on markDirty.
  let code_string: string | undefined = undefined
  let initial_code_string: string | undefined = undefined
  $: if (code_string !== undefined && initial_code_string === undefined) {
    initial_code_string = code_string
  }

  $: has_changes =
    has_typed ||
    name !== initial_name ||
    (initial_code_string !== undefined && code_string !== initial_code_string)

  export function getJudgeProperties(): V2EvalConfigProperties {
    return judge_fields.getProperties()
  }

  export function validateJudge(): string | null {
    return judge_fields.validate()
  }

  // ### Test Judge pane ###
  // Runs the drafted judge against a real task run before anything is saved,
  // via the task-scoped draft endpoint (no eval exists yet).

  let available_runs: TaskRunOutput[] = []
  let runs_loading = true
  let runs_error: KilnError | null = null
  let selected_task_run: TaskRunOutput | null = null
  let test_loading = false
  let test_error: KilnError | null = null
  let test_result: TestV2EvalResponse | null = null
  let test_has_valid_run = false
  let test_shape_warning: string | null = null
  let test_score_range_warning: string | null = null
  let test_abort_controller: AbortController | null = null
  let trust_dialog: TrustCodeDialog

  $: manual_example_support = manualExampleSupport(judge_type)

  onMount(async () => {
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
  })

  function select_task_run(run: TaskRunOutput) {
    selected_task_run = run
    test_result = null
    test_has_valid_run = false
    test_shape_warning = null
    test_score_range_warning = null
    test_error = null
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
    return eval_input
  }

  function validate_result_shape(scores: Record<string, number> | undefined): {
    valid: boolean
    message: string | null
  } {
    if (!scores || !output_scores.length) {
      return { valid: true, message: null }
    }
    const expected_keys = output_scores.map((s) => string_to_json_key(s.name))
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
    // result/warning/error on screen.
    test_error = null
    test_result = null
    test_has_valid_run = false
    test_shape_warning = null
    test_score_range_warning = null

    if (output_scores.length === 0) {
      test_error = createKilnError(
        new Error("Name your eval before testing the judge."),
      )
      return
    }

    const eval_input = build_eval_input()
    if (!eval_input) return

    const validation_error = judge_fields?.validate()
    if (validation_error) {
      test_error = createKilnError(new Error(validation_error))
      return
    }

    const controller = new AbortController()
    test_abort_controller = controller

    try {
      test_loading = true
      const result = await testV2EvalDraft(
        project_id,
        task_id,
        {
          properties: judge_fields.getProperties(),
          output_scores,
          eval_input,
        },
        controller.signal,
      )

      if (
        result.skipped_reason === "code_eval_not_trusted" &&
        judge_metadata.requiresTrust
      ) {
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

  async function grant_trust_and_retry_test(): Promise<boolean> {
    try {
      await addCodeTrust(project_id)
    } catch (e) {
      test_error = createKilnError(e)
      return false
    }
    run_test()
    return true
  }
</script>

<!--
  Grid so the form and the Test Judge pane sit side-by-side on wide screens,
  mirroring the add-judge builder. The pane lives outside FormContainer so its
  controls aren't validated on save. Collapses to a single column below xl.
-->
<div
  class="grid grid-cols-1 gap-y-6 xl:gap-x-16 xl:items-start xl:grid-cols-[minmax(0,1fr)_18rem] 2xl:grid-cols-[minmax(0,1fr)_24rem]"
>
  <div class="min-w-0 flex flex-col gap-6">
    <!-- Header and intro live above the form so "Judge Configuration" aligns
      with the Test Judge pane's header at the top of the grid row. -->
    <div class="text-xl font-bold">Judge Configuration</div>
    <EvalTypeIntro evalType={judge_type} metadata={judge_metadata} />
    <FormContainer
      submit_label="Save Eval"
      on:submit={() => dispatch("save")}
      bind:error
      bind:submitting
      compact_button={true}
      warn_before_unload={warn_before_unload && has_changes}
    >
      <FormElement
        label="Eval Name"
        description="A short name for your own reference."
        id="spec_name"
        bind:value={name}
        bind:error_message={name_error}
        validator={filename_string_short_validator}
      />

      <!--
    on:input/on:change catch edits to the judge's own fields, which this component
    doesn't own values for. "contents" keeps the wrapper out of the layout so
    FormContainer's spacing still applies to the children.
  -->
      <div
        class="flex flex-col gap-6 pt-2"
        on:input={markDirty}
        on:change={markDirty}
      >
        <JudgeConfigFields
          bind:this={judge_fields}
          eval_config_type={judge_type}
          bind:code_string
          {output_scores}
          code_placeholder_score_key={true}
          {project_id}
          {task_id}
        />
      </div>

      <!-- "contents" keeps this dirty-tracking wrapper out of the layout so
    FormContainer's spacing still applies to the Collapse. -->
      <div class="contents" on:input={markDirty} on:change={markDirty}>
        <Collapse title="Advanced Options">
          <FormElement
            label="Priority"
            id="priority"
            inputType="select"
            bind:value={priority}
            description="The priority level for this eval."
            select_options={[
              [0, "P0 - Critical"],
              [1, "P1 - High"],
              [2, "P2 - Medium"],
              [3, "P3 - Low"],
            ]}
          />
          <FormElement
            label="Evaluate Complete Agent History"
            id="evaluate_full_trace"
            inputType="checkbox"
            bind:value={evaluate_full_trace}
            disabled={full_trace_disabled}
            description="When enabled, this will be evaluated on the full agent history including intermediate steps and tool calls. When disabled, only the final answer is evaluated."
            info_description={full_trace_disabled
              ? `The ${judge_metadata.label} judge reads the agent's execution trace, so this eval always runs on the full history.`
              : "Enable this for evals that cover reasoning steps, tool usage, or intermediate outputs."}
          />
        </Collapse>
      </div>
    </FormContainer>
  </div>

  <div class="min-w-0">
    <EvalTestRunPane
      {project_id}
      {task_id}
      eval_config_type={judge_type}
      {runs_loading}
      {runs_error}
      {available_runs}
      selected_run={selected_task_run}
      {test_loading}
      {test_result}
      {test_error}
      {test_shape_warning}
      {test_score_range_warning}
      {test_has_valid_run}
      manual_example_supported={manual_example_support.supported}
      on:select={(e) => select_task_run(e.detail)}
      on:run={run_test}
      on:cancel={cancel_test}
      on:runAgain={run_test}
    />
  </div>
</div>

<TrustCodeDialog
  bind:this={trust_dialog}
  on_trust={grant_trust_and_retry_test}
/>
