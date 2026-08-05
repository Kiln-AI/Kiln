<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import type { InlineAction } from "$lib/utils/form_element.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { EvalOutputScore } from "$lib/types"
  import { generate_default_code, generate_examples } from "./code_eval_helpers"
  import { SHOW_REFERENCE_DATA_UI } from "$lib/utils/eval_types/reference_data_ui"
  import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"

  export let output_scores: EvalOutputScore[] | undefined = undefined

  // Creation flow: the score is named after the eval, which the user is still
  // typing. Rather than chasing the name field with regeneration, the starter
  // code uses a static "score_name_placeholder" key and the note above the
  // editor shows the real key live. Running the judge validates the returned
  // keys against the eval's scores.
  export let placeholder_score_key: boolean = false

  function initial_code(): string {
    if (placeholder_score_key) {
      return generate_default_code(placeholder_scores(output_scores))
    }
    return generate_default_code(output_scores)
  }

  function placeholder_scores(
    scores: EvalOutputScore[] | undefined,
  ): EvalOutputScore[] {
    return [
      {
        name: "score_name_placeholder",
        type: scores?.[0]?.type ?? "pass_fail",
      } as EvalOutputScore,
    ]
  }

  export let properties: components["schemas"]["CodeEvalProperties"] & {
    timeout_seconds?: number
  } = {
    type: "code_eval",
    code: initial_code(),
    reference_keys: [],
    timeout_seconds: 30,
  }

  // Bindable code string so the parent can track code edits reactively.
  export let code_string: string = properties.code

  let user_has_edited = false
  // The editor dispatches `change` for programmatic setValue too, so remember
  // what we generated ourselves: only a change that differs from our own
  // generation counts as a user edit. Without this, a programmatic
  // regeneration would mark the form as edited and freeze all further
  // regeneration.
  let last_generated_code = properties.code

  // In placeholder mode the starter is static by design — never regenerate.
  $: if (!placeholder_score_key && output_scores && !user_has_edited) {
    const new_code = generate_default_code(output_scores)
    last_generated_code = new_code
    properties.code = new_code
    code_string = new_code
    code_editor?.setValue(new_code)
  }

  // The keys the eval expects the score function to return.
  $: expected_score_keys = (output_scores ?? [])
    .map((score) => string_to_json_key(score.name))
    .filter((key) => key.length > 0)

  // Hidden while the eval name is empty or invalid (no keys to show yet).
  $: score_key_note =
    expected_score_keys.length > 0
      ? placeholder_score_key
        ? `Replace "score_name_placeholder" in the code below with the eval score key ${expected_score_keys
            .map((key) => `"${key}"`)
            .join(", ")}.`
        : `Your function must return the score key${
            expected_score_keys.length > 1 ? "s" : ""
          } ${expected_score_keys.map((key) => `"${key}"`).join(", ")}.`
      : null

  let timeout_seconds: number = properties.timeout_seconds ?? 30

  $: properties.timeout_seconds = timeout_seconds

  export function getProperties(): Omit<
    components["schemas"]["CodeEvalProperties"],
    "reference_keys"
  > & {
    timeout_seconds?: number
  } {
    return {
      type: "code_eval",
      code: properties.code,
      timeout_seconds,
    }
  }

  let examples_dialog: Dialog
  let active_example_tab: number = 0

  // In placeholder mode the examples use the placeholder key too: the real
  // key comes from the still-being-typed eval name (and would be an empty
  // string before the user names the eval).
  $: examples = generate_examples(
    placeholder_score_key ? placeholder_scores(output_scores) : output_scores,
  )

  function show_examples() {
    active_example_tab = 0
    examples_dialog.show()
  }

  function use_example(): boolean {
    properties.code = examples[active_example_tab].code
    code_string = examples[active_example_tab].code
    code_editor?.setValue(examples[active_example_tab].code)
    user_has_edited = true
    return true
  }

  let code_editor: CodeEditor

  const examples_inline_action: InlineAction = {
    handler: show_examples,
    label: "Examples",
  }

  function on_code_change(e: CustomEvent<string>) {
    properties.code = e.detail
    code_string = e.detail
    if (e.detail !== last_generated_code) {
      user_has_edited = true
    }
  }
</script>

<div class="flex flex-col gap-4">
  <FormElement
    id="code_eval_score_function"
    label="Score Function"
    description="Define a Python score function to evaluate the model's work."
    info_description={SHOW_REFERENCE_DATA_UI
      ? "The Python function can use the model's output, trace, and eval's reference data to drive pragmatic scoring. Faster and cheaper than LLM as a judge."
      : "The Python function can use the model's output and trace to drive pragmatic scoring. Faster and cheaper than LLM as a judge."}
    inputType="header_only"
    inline_action={examples_inline_action}
    value=""
  />
  {#if score_key_note}
    <div data-testid="score-key-note">
      <Warning
        warning_message={score_key_note}
        warning_color="primary"
        warning_icon="info"
        tight={true}
        text_size="xs"
      />
    </div>
  {/if}
  <CodeEditor
    bind:this={code_editor}
    value={properties.code || initial_code()}
    min_height="300px"
    on:change={on_code_change}
  />

  <FormElement
    id="code_eval_timeout"
    label="Timeout (seconds)"
    description="Maximum time allowed for the score function to execute. Must be between 1 and 300 seconds."
    inputType="input_number"
    bind:value={timeout_seconds}
    placeholder="30"
    min={1}
    max={300}
  />
</div>

<Dialog
  bind:this={examples_dialog}
  title="Code Judge Examples"
  width="wide"
  action_buttons={[
    {
      label: "Use This Example",
      isPrimary: true,
      action: use_example,
    },
  ]}
>
  <div class="flex flex-col gap-4">
    <div class="tabs tabs-bordered">
      {#each examples as example, i}
        <button
          type="button"
          class="tab {active_example_tab === i ? 'tab-active' : ''}"
          on:click={() => (active_example_tab = i)}
        >
          {example.label}
        </button>
      {/each}
    </div>
    <div
      class="bg-base-200 rounded-lg p-4 overflow-x-auto font-mono text-sm whitespace-pre"
    >
      {examples[active_example_tab].code}
    </div>
  </div>
</Dialog>
