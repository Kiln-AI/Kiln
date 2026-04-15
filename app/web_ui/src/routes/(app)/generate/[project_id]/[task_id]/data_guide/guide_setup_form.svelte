<script lang="ts" context="module">
  export type GuideSample = { input: string; output: string }
  export type GuideRule = { name: string; content: string }
</script>

<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import type { TaskRun, KilnAgentRunConfigProperties } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"
  import {
    fetch_few_shot_candidates,
    task_run_to_example,
  } from "$lib/utils/few_shot_example"
  import Dialog from "$lib/ui/dialog.svelte"
  import TableButton from "../table_button.svelte"
  import TaskRunPicker from "$lib/utils/task_run_picker.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"

  export let error: KilnError | null = null
  export let submitting: boolean = false
  export let project_id: string
  export let task_id: string

  // Local state for dialog FormContainers so they don't interfere with each other
  let dialog_error: KilnError | null = null
  let dialog_submitting: boolean = false

  // Unified examples list (manual + existing + saved golden)
  export let guide_examples: GuideSample[] = []
  // Rules list
  export let guide_rules: GuideRule[] = []

  // Build requirements markdown from rules
  export function build_requirements_markdown(): string {
    if (guide_rules.length === 0) return ""
    return guide_rules.map((r) => `## ${r.name}\n${r.content}`).join("\n\n")
  }

  // --- Example management ---
  let example_dialog: Dialog
  let example_mode: "add" | "edit" = "add"
  let example_add_method: "manual" | "existing" | null = null
  let editing_example_index: number = -1
  let editing_example_input: string = ""
  let editing_example_output: string = ""

  function open_add_example_dialog() {
    example_mode = "add"
    example_add_method = null
    editing_example_input = ""
    editing_example_output = ""
    editing_example_index = -1
    example_dialog?.show()
  }

  function open_edit_example_dialog(index: number) {
    example_mode = "edit"
    example_add_method = "manual"
    editing_example_index = index
    editing_example_input = guide_examples[index].input
    editing_example_output = guide_examples[index].output
    example_dialog?.show()
  }

  function save_example() {
    const sample: GuideSample = {
      input: editing_example_input,
      output: editing_example_output,
    }
    if (example_mode === "edit" && editing_example_index >= 0) {
      guide_examples[editing_example_index] = sample
      guide_examples = guide_examples
    } else {
      guide_examples = [...guide_examples, sample]
    }
    example_dialog?.close()
  }

  function remove_example(index: number) {
    guide_examples = guide_examples.filter((_, i) => i !== index)
  }

  // Few-shot selector for "Choose from Existing"
  let available_runs: TaskRun[] = []
  let loading_runs = true

  function select_existing_run(run: TaskRun) {
    const ex = task_run_to_example(run)
    guide_examples = [...guide_examples, { input: ex.input, output: ex.output }]
    example_dialog?.close()
  }

  onMount(async () => {
    try {
      const result = await fetch_few_shot_candidates(project_id, task_id)
      available_runs = result.available_runs.filter(
        (r) => r.input_source?.type !== "synthetic",
      )
    } catch {
      // Non-critical
    } finally {
      loading_runs = false
    }
    open_add_example_dialog()
  })

  // --- Rule management ---
  let rule_dialog: Dialog
  let rule_mode: "add" | "edit" = "add"
  let editing_rule_index: number = -1
  let editing_rule_name: string = ""
  let editing_rule_content: string = ""

  function open_add_rule_dialog() {
    rule_mode = "add"
    editing_rule_index = -1
    editing_rule_name = ""
    editing_rule_content = ""
    rule_dialog?.show()
  }

  function open_edit_rule_dialog(index: number) {
    rule_mode = "edit"
    editing_rule_index = index
    editing_rule_name = guide_rules[index].name
    editing_rule_content = guide_rules[index].content
    rule_dialog?.show()
  }

  function save_rule() {
    const rule: GuideRule = {
      name: editing_rule_name,
      content: editing_rule_content,
    }
    if (rule_mode === "edit" && editing_rule_index >= 0) {
      guide_rules[editing_rule_index] = rule
      guide_rules = guide_rules
    } else {
      guide_rules = [...guide_rules, rule]
    }
    rule_dialog?.close()
  }

  function remove_rule(index: number) {
    guide_rules = guide_rules.filter((_, i) => i !== index)
  }

  // --- Generate modal ---
  let generate_dialog: Dialog
  let run_config_component: RunConfigComponent | null = null

  function open_generate_dialog() {
    generate_dialog?.show()
  }

  function handle_generate_submit() {
    const run_config =
      run_config_component?.run_options_as_run_config_properties()
    if (!run_config) {
      error = new KilnError("Please select a model", null)
      return
    }
    if (!isKilnAgentRunConfig(run_config)) {
      error = new KilnError(
        "Task Data Guide requires a kiln_agent run config",
        null,
      )
      return
    }
    generate_dialog?.close()
    const all_examples = get_all_examples()
    dispatch("generate_preview", {
      selected_examples: all_examples,
      run_config,
    })
  }

  // --- Events ---
  const dispatch = createEventDispatcher<{
    generate_preview: {
      selected_examples: GuideSample[]
      run_config: KilnAgentRunConfigProperties
    }
  }>()

  export function get_all_examples(): GuideSample[] {
    return guide_examples.filter((e) => e.input.trim() || e.output.trim())
  }

  // --- Expandable rows ---
  let expanded_examples: boolean[] = []
  let prev_examples_len = 0
  $: if (guide_examples.length !== prev_examples_len) {
    prev_examples_len = guide_examples.length
    expanded_examples = new Array(guide_examples.length).fill(false)
  }

  function toggle_example_expand(index: number) {
    expanded_examples[index] = !expanded_examples[index]
    expanded_examples = expanded_examples
  }

  $: has_any_content =
    guide_examples.some((e) => e.input.trim() || e.output.trim()) ||
    guide_rules.length > 0
</script>

<FormContainer
  submit_label="Continue"
  on:submit={open_generate_dialog}
  bind:error={dialog_error}
  bind:submitting={dialog_submitting}
  compact_button={true}
>
  <!-- Example Data Section -->
  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <div>
        <div class="font-medium">Example Data</div>
        <div class="text-sm text-gray-500">
          Provide examples of real task data to guide synthetic generation.
        </div>
      </div>
      <button
        class="btn btn-sm btn-outline"
        on:click={open_add_example_dialog}
        type="button">+ Add Example</button
      >
    </div>

    {#if guide_examples.length > 0}
      <div class="rounded-lg border">
        <table class="table table-fixed">
          <thead>
            <tr>
              <th>Input</th>
              <th>Output</th>
              <th style="width: 50px"></th>
            </tr>
          </thead>
          <tbody>
            {#each guide_examples as example, i}
              <tr
                on:click={() => toggle_example_expand(i)}
                class="cursor-pointer"
              >
                <td class="py-2">
                  {#if expanded_examples[i]}
                    <pre
                      class="whitespace-pre-wrap break-words">{example.input}</pre>
                  {:else}
                    <div class="truncate">{example.input}</div>
                  {/if}
                </td>
                <td class="py-2">
                  {#if expanded_examples[i]}
                    <pre
                      class="whitespace-pre-wrap break-words">{example.output}</pre>
                  {:else}
                    <div class="truncate">{example.output}</div>
                  {/if}
                </td>
                <td class="py-2 p-0">
                  <div class="dropdown dropdown-end dropdown-hover">
                    <TableButton />
                    <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                    <ul
                      tabindex="0"
                      class="dropdown-content menu bg-base-100 rounded-box z-[1] w-40 p-2 shadow"
                    >
                      <li>
                        <button
                          on:click|stopPropagation={() =>
                            open_edit_example_dialog(i)}
                        >
                          Edit
                        </button>
                      </li>
                      <li>
                        <button
                          on:click|stopPropagation={() => remove_example(i)}
                        >
                          Remove
                        </button>
                      </li>
                    </ul>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <div
        class="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400"
      >
        No examples added yet.
      </div>
    {/if}
  </div>

  <!-- Rules & Descriptions Section -->
  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <div>
        <div class="font-medium">Rules & Descriptions</div>
        <div class="text-sm text-gray-500">
          Define rules, constraints, and structure for generated task inputs.
        </div>
      </div>
      <button
        class="btn btn-sm btn-outline"
        on:click={open_add_rule_dialog}
        type="button">+ Add Rule</button
      >
    </div>

    {#if guide_rules.length > 0}
      <div class="rounded-lg border">
        <table class="table table-fixed">
          <thead>
            <tr>
              <th style="width: 200px">Name</th>
              <th>Content</th>
              <th style="width: 50px"></th>
            </tr>
          </thead>
          <tbody>
            {#each guide_rules as rule, i}
              <tr>
                <td class="py-2">
                  <div class="truncate font-medium">{rule.name}</div>
                </td>
                <td class="py-2">
                  <div class="truncate">{rule.content}</div>
                </td>
                <td class="py-2 p-0">
                  <div class="dropdown dropdown-end dropdown-hover">
                    <TableButton />
                    <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                    <ul
                      tabindex="0"
                      class="dropdown-content menu bg-base-100 rounded-box z-[1] w-40 p-2 shadow"
                    >
                      <li>
                        <button
                          on:click|stopPropagation={() =>
                            open_edit_rule_dialog(i)}
                        >
                          Edit
                        </button>
                      </li>
                      <li>
                        <button on:click|stopPropagation={() => remove_rule(i)}>
                          Remove
                        </button>
                      </li>
                    </ul>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <div
        class="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-400"
      >
        No rules added yet.
      </div>
    {/if}
  </div>
</FormContainer>

<!-- Add/Edit Example Dialog -->
<Dialog
  bind:this={example_dialog}
  width="wide"
  title={example_mode === "edit" ? "Edit Example" : "Add Example"}
>
  {#if example_mode === "add" && example_add_method === null}
    <!-- Method selection -->
    <div class="flex flex-col gap-4 mt-4">
      {#if available_runs.length > 0}
        <button
          class="btn btn-outline"
          on:click={() => (example_add_method = "manual")}
          type="button"
        >
          Add Manually
        </button>
      {/if}

      {#if !loading_runs && available_runs.length > 0}
        <div class="flex items-center gap-2">
          <div class="flex-1 border-t border-base-300"></div>
          <span class="text-sm text-gray-400">or</span>
          <div class="flex-1 border-t border-base-300"></div>
        </div>

        <!-- Select from existing runs -->
        <div class="mt-4">
          {#if loading_runs}
            <div class="text-sm text-gray-400">Loading existing samples...</div>
          {:else}
            <TaskRunPicker
              {available_runs}
              on:select={(e) => select_existing_run(e.detail)}
            />
          {/if}
        </div>
      {/if}
    </div>
  {/if}
  {#if available_runs.length === 0 || example_add_method === "manual"}
    <!-- Manual input/output form -->
    <FormContainer
      submit_label={example_mode === "edit" ? "Save" : "Add"}
      on:submit={save_example}
      bind:error={dialog_error}
      bind:submitting={dialog_submitting}
      compact_button={true}
    >
      <FormElement
        label="Input"
        id="example_input"
        inputType="textarea"
        height="medium"
        bind:value={editing_example_input}
        optional={true}
        hide_optional_badge={true}
      />
      <FormElement
        label="Output"
        id="example_output"
        inputType="textarea"
        height="medium"
        bind:value={editing_example_output}
        optional={true}
        hide_optional_badge={true}
      />
    </FormContainer>
  {/if}
</Dialog>

<!-- Add/Edit Rule Dialog -->
<Dialog
  bind:this={rule_dialog}
  width="wide"
  title={rule_mode === "edit" ? "Edit Rule" : "Add Rule / Description"}
>
  <FormContainer
    submit_label={rule_mode === "edit" ? "Save" : "Add"}
    on:submit={save_rule}
    bind:error={dialog_error}
    bind:submitting={dialog_submitting}
    compact_button={true}
  >
    <FormElement label="Name" id="rule_name" bind:value={editing_rule_name} />
    <FormElement
      label="Content"
      id="rule_content"
      inputType="textarea"
      height="medium"
      bind:value={editing_rule_content}
    />
  </FormContainer>
</Dialog>

<!-- Generate Preview Modal -->
<Dialog
  bind:this={generate_dialog}
  title="Test Guide"
  sub_subtitle="Generate synthetic examples to preview how your guide performs."
>
  <FormContainer
    submit_label="Generate"
    on:submit={handle_generate_submit}
    bind:error={dialog_error}
    bind:submitting={dialog_submitting}
    compact_button={true}
  >
    <RunConfigComponent
      bind:this={run_config_component}
      {project_id}
      requires_structured_output={true}
      show_name_field={false}
      hide_prompt_selector={true}
      show_tools_selector_in_advanced={true}
      model_dropdown_settings={{
        requires_data_gen: true,
        suggested_mode: "data_gen",
      }}
    />
  </FormContainer>
</Dialog>
