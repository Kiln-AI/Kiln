<script lang="ts" context="module">
  export type GuideSample = {
    input: string
    output: string
    task_run_id?: string
  }
</script>

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import type { Task, KilnAgentRunConfigProperties } from "$lib/types"
  import { isKilnAgentRunConfig } from "$lib/types"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import RunOptionsTiles from "./run_options_tiles.svelte"
  import AddExampleDialog from "./add_example_dialog.svelte"
  import Warning from "$lib/ui/warning.svelte"

  export let project_id: string
  export let task_id: string
  // Optional — forwarded to the output run config dialog so it can mirror the
  // SDG output flow (prompt + tools/skills at top level, requires_structured_output
  // keyed off task.output_json_schema). Falls back to safe defaults if absent.
  export let task: Task | null = null

  // page_error is exported so the parent can surface async errors (e.g. a
  // failed preview API call) inline above the submit button instead of in a
  // separate top-level banner. Cleared by handle_continue on each new attempt.
  export let page_error: KilnError | null = null
  let page_submitting: boolean = false

  // Unified examples list (manual + existing + saved golden)
  export let guide_examples: GuideSample[] = []

  // Build the full data guide markdown from the user's examples — only the
  // `# Reference Examples` section. Rules are intentionally not collected
  // from the user here — the metaprompter generates them from refine
  // feedback on the first refine pass.
  function build_guide_md(): string {
    const valid_examples = guide_examples.filter(
      (e) => e.input.trim() || e.output.trim(),
    )
    if (valid_examples.length === 0) {
      return ""
    }
    const examples_body = valid_examples
      .map(
        (e, i) =>
          `## Example ${i + 1}\n\`\`\`input\n${e.input}\n\`\`\`\n\n\`\`\`output\n${e.output}\n\`\`\``,
      )
      .join("\n\n")
    return `# Reference Examples\n\n${examples_body}`
  }

  // --- Example management ---
  let add_example_dialog: AddExampleDialog
  function open_add_example_dialog() {
    add_example_dialog?.open_add()
  }
  function open_edit_example_dialog(index: number) {
    add_example_dialog?.open_edit(guide_examples[index], index)
  }
  function handle_example_submit(
    event: CustomEvent<{
      sample: GuideSample
      index: number
      mode: "add" | "edit"
    }>,
  ) {
    const { sample, index, mode } = event.detail
    if (mode === "edit" && index >= 0) {
      guide_examples[index] = sample
      guide_examples = guide_examples
    } else {
      guide_examples = [...guide_examples, sample]
    }
  }
  function remove_example(index: number) {
    guide_examples = guide_examples.filter((_, i) => i !== index)
  }

  $: has_examples = guide_examples.length > 0

  function open_generation_options() {
    run_options_tiles?.open_combined_dialog()
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
        guide: build_guide_md(),
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

<FormContainer
  submit_label="Continue"
  on:submit={handle_continue}
  bind:error={page_error}
  bind:submitting={page_submitting}
  submit_disabled={!has_examples}
  compact_button={true}
  warn_before_unload={has_examples}
>
  <!-- Example Data Section -->
  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <div>
        <div class="font-medium">Example Data</div>
        <div class="text-sm text-gray-500">
          Example task data to guide synthetic data generation.
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
        No examples
      </div>
    {/if}
  </div>

  <RunOptionsTiles
    bind:this={run_options_tiles}
    mode="link"
    {project_id}
    {task}
  />
  {#if !has_examples}
    <div class="flex justify-end">
      <Warning
        warning_message="Please provide at least one example."
        warning_color="error"
        warning_icon="exclaim"
        tight
      />
    </div>
  {/if}
</FormContainer>
<div class="flex justify-end mt-2">
  <button
    type="button"
    class="link text-sm text-gray-500 hover:text-gray-700"
    on:click={open_generation_options}
  >
    Generation options
  </button>
</div>

<AddExampleDialog
  bind:this={add_example_dialog}
  {project_id}
  {task_id}
  existing_examples={guide_examples}
  on:submit={handle_example_submit}
/>
