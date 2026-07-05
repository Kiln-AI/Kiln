<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import type { InlineAction } from "$lib/utils/form_element.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { EvalOutputScore } from "$lib/types"
  import { generate_default_code, generate_examples } from "./code_eval_helpers"

  export let output_scores: EvalOutputScore[] | undefined = undefined

  export let properties: components["schemas"]["CodeEvalProperties"] & {
    timeout_seconds?: number
  } = {
    type: "code_eval",
    code: generate_default_code(output_scores),
    timeout_seconds: 30,
  }

  let user_has_edited = false

  $: if (output_scores && !user_has_edited) {
    const new_code = generate_default_code(output_scores)
    properties.code = new_code
    code_editor?.setValue(new_code)
  }

  let timeout_seconds: number = properties.timeout_seconds ?? 30

  $: properties.timeout_seconds = timeout_seconds

  export function getProperties(): components["schemas"]["CodeEvalProperties"] & {
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

  $: examples = generate_examples(output_scores)

  function show_examples() {
    active_example_tab = 0
    examples_dialog.show()
  }

  function use_example(): boolean {
    properties.code = examples[active_example_tab].code
    code_editor?.setValue(examples[active_example_tab].code)
    user_has_edited = true
    return true
  }

  let code_editor: CodeEditor

  const examples_inline_action: InlineAction = {
    handler: show_examples,
    label: "More Examples",
  }

  function on_code_change(e: CustomEvent<string>) {
    properties.code = e.detail
    user_has_edited = true
  }
</script>

<div class="flex flex-col gap-4">
  <FormElement
    id="code_eval_score_function"
    label="Score Function"
    description="Define a Python score function to evaluate the model's work."
    info_description="The Python function can use the model's output, trace, and eval's reference data to drive pragmatic scoring. Faster and cheaper than LLM as a judge."
    inputType="header_only"
    inline_action={examples_inline_action}
    value=""
  />
  <CodeEditor
    bind:this={code_editor}
    value={properties.code || generate_default_code(output_scores)}
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
  title="Code Eval Examples"
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
