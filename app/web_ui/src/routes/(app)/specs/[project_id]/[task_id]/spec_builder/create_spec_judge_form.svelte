<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import JudgeConfigFields from "$lib/components/eval_types/judge_config_fields.svelte"
  import EvalTypeIntro from "$lib/components/eval_types/eval_type_intro.svelte"
  import { getV2EvalTypeMetadata } from "$lib/utils/eval_types/registry"
  import type { V2EvalType } from "$lib/utils/eval_types/registry"
  import type { V2EvalConfigProperties } from "$lib/api/v2_eval_api"
  import { filename_string_short_validator } from "$lib/utils/input_validators"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { Priority } from "$lib/types"

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
</script>

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
    <div class="text-xl font-bold">Judge Configuration</div>
    <EvalTypeIntro evalType={judge_type} metadata={judge_metadata} />
    <JudgeConfigFields
      bind:this={judge_fields}
      eval_config_type={judge_type}
      bind:code_string
      {project_id}
      {task_id}
    />
  </div>

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
</FormContainer>
