<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import CodeEditor from "$lib/components/code_editor.svelte"
  import Dialog from "$lib/ui/dialog.svelte"

  const DEFAULT_CODE = `def score(output, trace, reference_data, task_input, kiln):
    """Score the model output.

    Args:
        output: The model's final output string.
        trace: List of message dicts from the conversation.
        reference_data: Dict of reference/expected data (if any).
        task_input: The original task input string.
        kiln: KilnEvalHelpers with utility methods.

    Returns:
        A dict of score names to float values (0.0 to 1.0).
    """
    if not output:
        return {"quality": 0.0}
    return {"quality": 1.0}
`

  export let properties: components["schemas"]["CodeEvalProperties"] & {
    timeout_seconds?: number
  } = {
    type: "code_eval",
    code: DEFAULT_CODE,
    timeout_seconds: 30,
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

  const examples = [
    {
      label: "Parse JSON",
      code: `import json

def score(output, trace, reference_data, task_input, kiln):
    """Check if the output is valid JSON with required fields."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return {"valid_json": 0.0, "has_fields": 0.0}

    required = ["name", "description"]
    has_all = all(k in data for k in required)
    return {
        "valid_json": 1.0,
        "has_fields": kiln.pass_fail(has_all),
    }
`,
    },
    {
      label: "Check tool usage",
      code: `def score(output, trace, reference_data, task_input, kiln):
    """Verify the model used the expected tools."""
    tool_calls = kiln.get_tool_calls(trace)
    used_search = kiln.has_tool_call(tool_calls, "search")
    call_count = kiln.count_tool_calls(tool_calls, "search")

    return {
        "used_search": kiln.pass_fail(used_search),
        "search_count": kiln.five_star(min(call_count, 5)),
    }
`,
    },
    {
      label: "Domain-specific grading",
      code: `def score(output, trace, reference_data, task_input, kiln):
    """Grade output against domain-specific criteria."""
    expected = (reference_data or {}).get("expected_answer", "")

    kiln.assert_contains(output, expected)

    word_count = len(output.split())
    concise = 10 <= word_count <= 200

    return {
        "contains_answer": 1.0,
        "conciseness": kiln.pass_fail(concise),
        "length_score": kiln.five_star(
            5 if word_count < 50 else 3 if word_count < 150 else 1
        ),
    }
`,
    },
  ]

  function show_examples() {
    active_example_tab = 0
    examples_dialog.show()
  }

  function use_example(): boolean {
    properties.code = examples[active_example_tab].code
    code_editor?.setValue(examples[active_example_tab].code)
    return true
  }

  let code_editor: CodeEditor

  function on_code_change(e: CustomEvent<string>) {
    properties.code = e.detail
  }
</script>

<div class="flex flex-col gap-4">
  <div class="flex items-center gap-2">
    <span class="badge badge-sm badge-primary badge-outline font-medium"
      >Beta</span
    >
    <span class="text-xs text-gray-500"
      >Write a Python function that scores model outputs.</span
    >
  </div>

  <div class="flex flex-col gap-1">
    <div class="flex items-center justify-between">
      <label for="code_eval_code" class="label">
        <span class="label-text font-medium">Score Function</span>
      </label>
      <button
        type="button"
        class="btn btn-ghost btn-xs text-primary"
        on:click={show_examples}
      >
        <i class="bi bi-code-square"></i>
        See examples
      </button>
    </div>
    <CodeEditor
      bind:this={code_editor}
      value={properties.code || DEFAULT_CODE}
      min_height="300px"
      on:change={on_code_change}
    />
    <div class="text-xs text-gray-400 mt-1">
      Define a <code class="font-mono text-gray-500"
        >score(output, trace, reference_data, task_input, kiln)</code
      > function that returns a dict of score names to floats (0.0 - 1.0).
    </div>
  </div>

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
      label: "Cancel",
      isCancel: true,
    },
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
