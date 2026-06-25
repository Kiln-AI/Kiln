<script lang="ts">
  import type { components } from "$lib/api_schema"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import FormSection from "./form_parts/form_section.svelte"

  type ToolCallSpec = components["schemas"]["ToolCallSpec"]

  export let properties: components["schemas"]["ToolCallCheckProperties"] = {
    type: "tool_call_check",
    expected_tools: [],
    match_mode: "all",
    on_unexpected_tools: "ignore",
  }

  type ArgMatch = components["schemas"]["ArgMatch"]
  type ArgRow = { name: string; value: string; match_mode: string }

  const empty_tool: ToolCallSpec = {
    tool_name: "",
    expected_args: null,
  }

  let arg_rows: ArgRow[][] = properties.expected_tools.map((tool) =>
    tool.expected_args
      ? Object.entries(tool.expected_args).map(([name, arg]) => ({
          name,
          value: JSON.stringify(arg.value),
          match_mode: arg.match_mode ?? "exact",
        }))
      : [],
  )

  function sync_args_to_properties() {
    for (let i = 0; i < properties.expected_tools.length; i++) {
      const rows = arg_rows[i]
      if (!rows || rows.length === 0) {
        properties.expected_tools[i].expected_args = null
        continue
      }
      const args: Record<string, ArgMatch> = {}
      for (const row of rows) {
        if (!row.name.trim()) continue
        let parsed: unknown
        try {
          parsed = JSON.parse(row.value)
        } catch {
          parsed = row.value
        }
        args[row.name.trim()] = {
          value: parsed as ArgMatch["value"],
          match_mode: row.match_mode as ArgMatch["match_mode"],
        }
      }
      properties.expected_tools[i].expected_args =
        Object.keys(args).length > 0 ? args : null
    }
  }

  export function getProperties(): components["schemas"]["ToolCallCheckProperties"] {
    sync_args_to_properties()
    return properties
  }

  export function validate(): string | null {
    if (!properties.expected_tools || properties.expected_tools.length === 0) {
      return "At least one expected tool must be defined."
    }
    for (let i = 0; i < properties.expected_tools.length; i++) {
      if (!properties.expected_tools[i].tool_name.trim()) {
        return `Expected Tool #${i + 1} is missing a name.`
      }
    }
    return null
  }

  function add_arg(tool_index: number) {
    while (arg_rows.length <= tool_index) {
      arg_rows.push([])
    }
    arg_rows[tool_index] = [
      ...arg_rows[tool_index],
      { name: "", value: "", match_mode: "exact" },
    ]
    arg_rows = arg_rows
  }

  function remove_arg(tool_index: number, arg_index: number) {
    arg_rows[tool_index] = arg_rows[tool_index].filter(
      (_, i) => i !== arg_index,
    )
    arg_rows = arg_rows
  }
</script>

<div class="flex flex-col gap-6">
  <FormSection
    title="Expected Tools"
    subtitle={properties.match_mode === "never"
      ? "Define the tools the agent must NOT call. Tool calls are function calls the model makes during its reasoning trace."
      : "Define the tools the agent is expected to call. Tool calls are function calls the model makes during its reasoning trace."}
    testid="tool-call-expected-tools-section"
  >
    <FormList
      bind:content={properties.expected_tools}
      content_label="Expected Tool"
      empty_content={structuredClone(empty_tool)}
      let:item_index
    >
      <div class="ml-4 border-l border-base-300 pl-4">
        <div class="flex flex-col gap-2">
          <FormElement
            id="tool_name_{item_index}"
            label="Tool Name"
            description="The name of the tool that should be called."
            inputType="input"
            bind:value={properties.expected_tools[item_index].tool_name}
          />

          <Collapse
            title="Expected Arguments"
            description="Optionally check specific argument values passed to this tool."
            open={(arg_rows[item_index] ?? []).length > 0}
          >
            {#each arg_rows[item_index] ?? [] as arg_row, arg_index}
              <div class="flex gap-2 items-end">
                <div class="flex-1">
                  <FormElement
                    id="arg_name_{item_index}_{arg_index}"
                    label={arg_index === 0 ? "Arg Name" : ""}
                    inputType="input"
                    placeholder="arg name"
                    bind:value={arg_row.name}
                  />
                </div>
                <div class="flex-1">
                  <FormElement
                    id="arg_value_{item_index}_{arg_index}"
                    label={arg_index === 0 ? "Expected Value (JSON)" : ""}
                    info_description={arg_index === 0
                      ? 'Values must be valid JSON. Strings must be quoted (e.g. "hello"), numbers and booleans are bare (e.g. 42, true).'
                      : ""}
                    inputType="input"
                    placeholder={'"hello", 42, true'}
                    bind:value={arg_row.value}
                  />
                </div>
                <div class="w-32">
                  <FormElement
                    id="arg_match_{item_index}_{arg_index}"
                    label={arg_index === 0 ? "Comparison" : ""}
                    inputType="select"
                    bind:value={arg_row.match_mode}
                    select_options={[
                      ["exact", "Exact"],
                      ["contains", "Contains"],
                      ["regex", "Regex"],
                    ]}
                  />
                </div>
                <button
                  class="link text-xs text-gray-500"
                  on:click={() => remove_arg(item_index, arg_index)}
                  title="Remove argument"
                >
                  remove
                </button>
              </div>
            {/each}
            <button
              class="btn btn-ghost btn-sm self-start"
              on:click={() => add_arg(item_index)}
            >
              + Add Expected Argument
            </button>
          </Collapse>
        </div>
      </div>
    </FormList>
  </FormSection>

  <FormSection
    title="Match Mode"
    subtitle="How to match tools against the trace."
    testid="tool-call-match-mode-section"
  >
    <FormElement
      id="tool_call_check_match_mode"
      inputType="radio"
      radio_options={[
        {
          value: "any",
          label: "Any",
          description: "Pass if at least one of the expected tools was called.",
        },
        {
          value: "all",
          label: "All (any order)",
          description: "Pass if every expected tool was called, in any order.",
        },
        {
          value: "ordered",
          label: "Ordered (in list order)",
          description:
            "Pass if all expected tools were called in the order listed.",
        },
        {
          value: "never",
          label: "Never",
          description: "Pass if none of the listed tools were called.",
        },
      ]}
      bind:value={properties.match_mode}
      hide_label
    />
  </FormSection>

  {#if properties.match_mode !== "never"}
    <FormSection
      title="Unlisted Tool Calls"
      subtitle="What happens when the model calls tools not in your list."
      testid="tool-call-unexpected-section"
    >
      <FormElement
        id="tool_call_check_on_unexpected"
        inputType="radio"
        radio_options={[
          {
            value: "ignore",
            label: "Allow",
            description:
              "Extra tool calls beyond the expected list are allowed.",
          },
          {
            value: "fail",
            label: "Fail",
            description:
              "Fail if any tool is called that is not in the expected list.",
          },
        ]}
        bind:value={properties.on_unexpected_tools}
        hide_label
      />
    </FormSection>
  {/if}
</div>
