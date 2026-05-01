<script lang="ts" context="module">
  export type GuideSample = {
    input: string
    output: string
    task_run_id?: string
  }
  export type GuideRule = { name: string; content: string }
</script>

<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import type { TaskRun, Task, KilnAgentRunConfigProperties } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"
  import {
    fetch_task_sample_candidates,
    task_run_to_example,
  } from "$lib/utils/task_sample_example"
  import Dialog from "$lib/ui/dialog.svelte"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import TaskRunPicker from "$lib/utils/task_run_picker.svelte"
  import RunOptionsTiles from "./run_options_tiles.svelte"
  import Intro from "$lib/ui/intro.svelte"
  import DatabaseIcon from "$lib/ui/icons/database_icon.svelte"

  export let project_id: string
  export let task_id: string
  // Optional — forwarded to the output run config dialog so it can mirror the
  // SDG output flow (prompt + tools/skills at top level, requires_structured_output
  // keyed off task.output_json_schema). Falls back to safe defaults if absent.
  export let task: Task | null = null

  // Each FormContainer needs its own state so dialogs don't share spinners/errors.
  // page_error is exported so the parent can surface async errors (e.g. a
  // failed preview API call) inline above the submit button instead of in a
  // separate top-level banner. Cleared by handle_continue on each new attempt.
  export let page_error: KilnError | null = null
  let page_submitting: boolean = false
  let rule_error: KilnError | null = null
  let rule_submitting: boolean = false

  // Unified examples list (manual + existing + saved golden)
  export let guide_examples: GuideSample[] = []
  // Rules list
  export let guide_rules: GuideRule[] = []

  // Build the complete guide prompt from examples + rules
  function build_guide_markdown(): string {
    const parts: string[] = []

    const valid_examples = guide_examples.filter(
      (e) => e.input.trim() || e.output.trim(),
    )
    if (valid_examples.length > 0) {
      const example_text = valid_examples
        .map(
          (e, i) =>
            `## Example ${i + 1}\n\`\`\`input\n${e.input}\n\`\`\`\n\n\`\`\`output\n${e.output}\n\`\`\``,
        )
        .join("\n\n")
      parts.push(`# Reference Examples\n\n${example_text}`)
    }

    if (guide_rules.length > 0) {
      const rules_text = guide_rules
        .map((r) => `## ${r.name}\n${r.content}`)
        .join("\n\n")
      parts.push(`# Guidelines & Rules\n\n${rules_text}`)
    }

    return (
      parts.join("\n\n") || "Generate diverse, realistic inputs for this task."
    )
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
    const existing = guide_examples[editing_example_index]
    const sample: GuideSample = {
      input: editing_example_input,
      output: editing_example_output,
      task_run_id: example_mode === "edit" ? existing?.task_run_id : undefined,
    }
    if (example_mode === "edit" && editing_example_index >= 0) {
      guide_examples[editing_example_index] = sample
      guide_examples = guide_examples
    } else {
      guide_examples = [...guide_examples, sample]
    }
    intro_dismissed = true
    example_dialog?.close()
  }

  function remove_example(index: number) {
    guide_examples = guide_examples.filter((_, i) => i !== index)
  }

  // Few-shot selector for "Choose from Existing"
  let available_runs: TaskRun[] = []
  let loading_runs = true

  $: added_run_ids = new Set(
    guide_examples.map((e) => e.task_run_id).filter((id): id is string => !!id),
  )
  $: filtered_available_runs = available_runs.filter(
    (r) => !r.id || !added_run_ids.has(r.id),
  )

  function select_existing_run(run: TaskRun) {
    const ex = task_run_to_example(run)
    guide_examples = [
      ...guide_examples,
      { input: ex.input, output: ex.output, task_run_id: run.id ?? undefined },
    ]
    intro_dismissed = true
    example_dialog?.close()
  }

  onMount(async () => {
    try {
      const result = await fetch_task_sample_candidates(project_id, task_id)
      available_runs = result.available_runs.filter(
        (r) => r.input_source?.type !== "synthetic",
      )
    } catch {
      // Non-critical
    } finally {
      loading_runs = false
    }
  })

  // Intro state. We pin past the intro the moment the user actually adds an
  // example or a rule — clicking the Intro's primary button just opens the
  // modal so they can still cancel out and stay on the intro.
  let intro_dismissed: boolean = false
  $: has_examples = guide_examples.length > 0
  $: has_rules = guide_rules.length > 0
  $: show_intro = !intro_dismissed && !has_examples && !has_rules

  function open_generation_options() {
    run_options_tiles?.open_combined_dialog()
  }

  // --- Rule management ---
  let rule_dialog: Dialog
  let rule_mode: "add" | "edit" = "add"
  let editing_rule_index: number = -1
  let editing_rule_name: string = ""
  let editing_rule_content: string = ""
  // Bumped each time the rule dialog opens so the FormContainer/FormElements
  // remount with fresh state. Without this, FormElement's reactive validator
  // fires when we reset values back to "" between opens and surfaces a stale
  // "Title is required" error before the user has touched the field.
  let rule_form_token: number = 0

  function open_add_rule_dialog() {
    rule_mode = "add"
    editing_rule_index = -1
    editing_rule_name = ""
    editing_rule_content = ""
    rule_form_token++
    rule_dialog?.show()
  }

  function open_edit_rule_dialog(index: number) {
    rule_mode = "edit"
    editing_rule_index = index
    editing_rule_name = guide_rules[index].name
    editing_rule_content = guide_rules[index].content
    rule_form_token++
    rule_dialog?.show()
  }

  function save_rule() {
    // FormContainer sets rule_submitting=true before dispatching submit.
    // This handler is synchronous, so we have to flip it back ourselves —
    // otherwise the next time the dialog opens (with a fresh form via {#key}),
    // the bound rule_submitting is still true and the Add button spins.
    try {
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
    } finally {
      rule_submitting = false
    }
  }

  function remove_rule(index: number) {
    guide_rules = guide_rules.filter((_, i) => i !== index)
  }

  // --- Run options (per-stage) ---
  // Bound to the shared RunOptionsTiles instance so we can pull the configured
  // run configs at submit time.
  let run_options_tiles: RunOptionsTiles | null = null

  function handle_continue() {
    // FormContainer flips submitting=true before dispatching submit, and expects
    // us to flip it back if we don't proceed. Otherwise the Continue button
    // keeps spinning after a synchronous validation failure.
    page_error = null
    try {
      const valid_examples = guide_examples.filter(
        (e) => e.input.trim() || e.output.trim(),
      )
      if (valid_examples.length === 0) {
        page_error = new KilnError("At least one example is required.")
        return
      }
      const input_run_config = run_options_tiles?.get_input_run_config()
      const output_run_config = run_options_tiles?.get_output_run_config()
      if (!input_run_config || !output_run_config) {
        page_error = new KilnError(
          "Please select a model for input and output generation.",
          null,
        )
        return
      }
      if (
        !isKilnAgentRunConfig(input_run_config) ||
        !isKilnAgentRunConfig(output_run_config)
      ) {
        page_error = new KilnError(
          "Task Data Guide requires a kiln_agent run config.",
          null,
        )
        return
      }
      dispatch("generate_preview", {
        guide: build_guide_markdown(),
        input_run_config,
        output_run_config,
      })
    } finally {
      page_submitting = false
    }
  }

  // --- Events ---
  const dispatch = createEventDispatcher<{
    generate_preview: {
      guide: string
      input_run_config: KilnAgentRunConfigProperties
      output_run_config: KilnAgentRunConfigProperties
    }
  }>()

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
</script>

{#if show_intro}
  <div class="flex flex-col items-center justify-center min-h-[40vh] mt-8">
    <Intro
      title="Help us understand your task data with examples"
      description_paragraphs={[
        "Examples will help us generate higher-quality synthetic data tailored to your task.",
      ]}
      action_buttons={[
        {
          label: "Add Examples",
          onClick: open_add_example_dialog,
          is_primary: true,
        },
        {
          label: "Docs & Guide",
          href: "https://docs.kiln.tech/docs/synthetic-data-generation",
          new_tab: true,
          is_primary: false,
        },
      ]}
    >
      <div slot="icon" class="w-12 h-12">
        <DatabaseIcon />
      </div>
    </Intro>
  </div>
{:else}
  <FormContainer
    submit_label="Continue"
    on:submit={handle_continue}
    bind:error={page_error}
    bind:submitting={page_submitting}
    submit_visible={has_examples}
    compact_button={true}
    warn_before_unload={has_examples || has_rules}
  >
    <!-- Example Data Section -->
    <div class="flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <div>
          <div class="font-medium">Example Data</div>
          <div class="text-sm text-gray-500">
            Provide examples of real task data to guide synthetic data
            generation.
          </div>
        </div>
        <button
          class="btn btn-sm {has_examples
            ? 'btn-outline btn-primary'
            : 'btn-primary'}"
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
                      <TableActionMenu
                        items={[
                          {
                            label: "Edit",
                            onclick: () => open_edit_example_dialog(i),
                          },
                          { label: "Remove", onclick: () => remove_example(i) },
                        ]}
                      />
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
          <div class="font-medium">Guidelines & Rules</div>
          <div class="text-sm text-gray-500">
            Define the rules, constraints, and format for generated inputs and
            outputs.
          </div>
        </div>
        <button
          class="btn btn-sm {has_examples
            ? 'btn-outline btn-primary'
            : 'btn-primary'}"
          on:click={open_add_rule_dialog}
          type="button">+ Add Rule</button
        >
      </div>

      {#if guide_rules.length > 0}
        <div class="rounded-lg border">
          <table class="table table-fixed">
            <thead>
              <tr>
                <th style="width: 200px">Title</th>
                <th>Description</th>
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
                      <TableActionMenu
                        items={[
                          {
                            label: "Edit",
                            onclick: () => open_edit_rule_dialog(i),
                          },
                          { label: "Remove", onclick: () => remove_rule(i) },
                        ]}
                      />
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
          No rules added yet. (Optional)
        </div>
      {/if}
    </div>

    <RunOptionsTiles
      bind:this={run_options_tiles}
      mode="link"
      {project_id}
      {task}
    />
  </FormContainer>
  {#if has_examples}
    <div class="flex justify-end mt-2">
      <button
        type="button"
        class="link text-sm text-gray-500 hover:text-gray-700"
        on:click={open_generation_options}
      >
        Generation options
      </button>
    </div>
  {/if}
{/if}

<!-- Add/Edit Example Dialog -->
<Dialog
  bind:this={example_dialog}
  width="wide"
  title={example_mode === "edit" ? "Edit Example" : "Add Example"}
  sub_subtitle="Provide a real example of task data to guide generation."
>
  {#if example_mode === "add" && example_add_method === null}
    <!-- Method selection -->
    <div class="flex flex-col gap-4 mt-8">
      {#if filtered_available_runs.length > 0}
        <button
          class="btn btn-outline mb-2"
          on:click={() => (example_add_method = "manual")}
          type="button"
        >
          Add Manually
        </button>
      {/if}

      {#if !loading_runs && filtered_available_runs.length > 0}
        <div class="flex items-center gap-2">
          <div class="flex-1 border-t border-base-300"></div>
          <span class="text-sm text-gray-400">or Select Existing</span>
          <div class="flex-1 border-t border-base-300"></div>
        </div>

        <!-- Select from existing runs -->
        <div class="flex flex-col mt-2 gap-2">
          {#if loading_runs}
            <div class="text-sm text-gray-400">Loading existing samples...</div>
          {:else}
            <TaskRunPicker
              available_runs={filtered_available_runs}
              on:select={(e) => select_existing_run(e.detail)}
            />
          {/if}
        </div>
      {/if}
    </div>
  {/if}
  {#if filtered_available_runs.length === 0 || example_add_method === "manual"}
    <!-- Manual input/output form -->
    <div class="flex flex-col gap-3">
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
      <div class="flex flex-row gap-2 justify-end mt-2">
        {#if example_mode === "add" && filtered_available_runs.length > 0 && available_runs.length > 0}
          <button
            type="button"
            class="btn btn-sm h-10 btn-outline min-w-24"
            on:click={() => (example_add_method = null)}
          >
            Back
          </button>
        {/if}
        <button
          type="button"
          class="btn btn-sm h-10 btn-primary min-w-24"
          on:click={save_example}
        >
          {example_mode === "edit" ? "Save" : "Add"}
        </button>
      </div>
    </div>
  {/if}
</Dialog>

<!-- Add/Edit Rule Dialog -->
<Dialog
  bind:this={rule_dialog}
  width="wide"
  title={rule_mode === "edit" ? "Edit Rule" : "Add Guideline or Rule"}
  sub_subtitle="Specify how inputs and outputs should behave."
>
  {#key rule_form_token}
    <FormContainer
      submit_label={rule_mode === "edit" ? "Save" : "Add"}
      on:submit={save_rule}
      bind:error={rule_error}
      bind:submitting={rule_submitting}
      compact_button={true}
    >
      <FormElement
        label="Title"
        id="rule_name"
        bind:value={editing_rule_name}
        placeholder="e.g. Realistic User Scenarios"
      />
      <FormElement
        label="Description"
        id="rule_content"
        inputType="textarea"
        height="medium"
        placeholder="e.g. Include realistic user scenarios in the input to help the model generate more relevant outputs."
        bind:value={editing_rule_content}
      />
    </FormContainer>
  {/key}
</Dialog>
