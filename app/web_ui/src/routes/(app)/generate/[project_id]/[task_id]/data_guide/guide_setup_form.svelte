<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import type { KilnError } from "$lib/utils/error_handlers"
  import type { TaskRun } from "$lib/types"
  import {
    fetch_few_shot_candidates,
    task_run_to_example,
  } from "$lib/utils/few_shot_example"
  import Dialog from "$lib/ui/dialog.svelte"

  type GuideSample = { input: string; output: string }

  export let requirements: string = ""
  export let examples: string | null = null
  export let error: KilnError | null = null
  export let submitting: boolean = false
  export let existing_samples: GuideSample[] = []
  export let project_id: string
  export let task_id: string

  // Manual examples list
  let manual_examples: GuideSample[] = []

  function add_manual_example() {
    manual_examples = [...manual_examples, { input: "", output: "" }]
  }

  function remove_manual_example(index: number) {
    manual_examples = manual_examples.filter((_, i) => i !== index)
  }

  // Few-shot selector
  let available_runs: TaskRun[] = []
  let loading_runs = true
  let selected_run: TaskRun | null = null

  // Preview dialog
  let preview_dialog: Dialog
  let previewing_run: TaskRun | null = null
  const PAGE_SIZE = 5
  let current_page = 0
  $: total_pages = Math.ceil(available_runs.length / PAGE_SIZE)
  $: paged_runs = available_runs.slice(
    current_page * PAGE_SIZE,
    (current_page + 1) * PAGE_SIZE,
  )

  function show_preview(run: TaskRun, event: MouseEvent) {
    if ((event.target as HTMLElement).closest("button")) return
    previewing_run = run
    preview_dialog?.show()
  }

  function select_run(run: TaskRun) {
    selected_run = run
  }

  function clear_selection() {
    selected_run = null
  }

  onMount(async () => {
    try {
      const result = await fetch_few_shot_candidates(project_id, task_id)
      // Filter out synthetic runs
      available_runs = result.available_runs.filter(
        (r) => r.input_source?.type !== "synthetic",
      )
    } catch {
      // Non-critical
    } finally {
      loading_runs = false
    }
  })

  const dispatch = createEventDispatcher<{
    generate_preview: {
      selected_examples: GuideSample[]
    }
    generate_without_samples: void
  }>()

  function get_all_examples(): GuideSample[] {
    const examples: GuideSample[] = []

    // Add selected run
    if (selected_run) {
      const ex = task_run_to_example(selected_run)
      examples.push(ex)
    }

    // Add manual examples (only non-empty ones)
    for (const m of manual_examples) {
      if (m.input.trim() || m.output.trim()) {
        examples.push({ input: m.input, output: m.output })
      }
    }

    // Add existing saved samples
    examples.push(...existing_samples)

    return examples
  }

  $: has_any_example =
    selected_run !== null ||
    manual_examples.some((m) => m.input.trim() || m.output.trim()) ||
    existing_samples.length > 0
</script>

<FormContainer
  submit_label="Generate synthetic examples"
  on:submit={() =>
    dispatch("generate_preview", { selected_examples: get_all_examples() })}
  bind:error
  bind:submitting
  warn_before_unload={true}
>
  <div class="flex flex-col gap-6">
    <!-- Example Data Section -->
    <div class="flex flex-col gap-2">
      <div class="font-medium">Example Data</div>
      <div class="text-sm text-gray-500">
        Provide examples of real task data to guide synthetic generation.
        Examples help produce higher quality, more realistic inputs.
      </div>
    </div>

    <!-- Existing saved samples -->
    {#if existing_samples.length > 0}
      <div class="flex flex-col gap-2">
        <div class="text-sm font-medium">
          Saved Golden Examples
          <span class="font-normal text-gray-500"
            >({existing_samples.length})</span
          >
        </div>
        <div class="rounded-lg border">
          <table class="table table-fixed">
            <thead>
              <tr>
                <th>Input</th>
                <th>Output</th>
              </tr>
            </thead>
            <tbody>
              {#each existing_samples as sample}
                <tr>
                  <td class="py-2">
                    <pre
                      class="whitespace-pre-wrap break-words">{sample.input}</pre>
                  </td>
                  <td class="py-2">
                    <pre
                      class="whitespace-pre-wrap break-words">{sample.output}</pre>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}

    <!-- Select from existing data -->
    {#if loading_runs}
      <div class="text-sm text-gray-400">Loading existing samples...</div>
    {:else if available_runs.length > 0}
      <div class="flex flex-col gap-2">
        <div class="text-sm font-medium">Select from Existing Data</div>
        {#if selected_run}
          <div class="rounded-lg border p-3 flex items-start gap-3">
            <div class="flex-grow min-w-0">
              <div class="text-xs text-gray-500 mb-1">Selected example</div>
              <div class="truncate text-sm">{selected_run.input ?? ""}</div>
            </div>
            <button
              class="btn btn-xs btn-ghost"
              on:click={clear_selection}
              type="button">Change</button
            >
          </div>
        {:else}
          <div class="rounded-lg border">
            <table class="table table-fixed">
              <thead>
                <tr>
                  <th>Input</th>
                  <th>Output</th>
                  <th style="width: 80px"></th>
                </tr>
              </thead>
              <tbody>
                {#each paged_runs as run}
                  <tr
                    class="cursor-pointer hover:bg-base-200"
                    on:click={(e) => show_preview(run, e)}
                  >
                    <td class="py-2">
                      <div class="truncate">{run.input ?? ""}</div>
                    </td>
                    <td class="py-2">
                      <div class="truncate">
                        {run.output?.output ?? ""}
                      </div>
                    </td>
                    <td class="py-2">
                      <button
                        class="btn btn-xs btn-outline"
                        on:click|stopPropagation={() => select_run(run)}
                        type="button">Select</button
                      >
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
            {#if total_pages > 1}
              <div class="flex justify-center gap-2 py-2">
                <button
                  class="btn btn-xs"
                  disabled={current_page === 0}
                  on:click={() => (current_page = current_page - 1)}
                  type="button">Prev</button
                >
                <span class="text-xs text-gray-500 self-center"
                  >{current_page + 1} / {total_pages}</span
                >
                <button
                  class="btn btn-xs"
                  disabled={current_page >= total_pages - 1}
                  on:click={() => (current_page = current_page + 1)}
                  type="button">Next</button
                >
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}

    <!-- Manual examples -->
    <div class="flex flex-col gap-2">
      <div class="text-sm font-medium">Manual Examples</div>
      {#each manual_examples as example, i}
        <div class="rounded-lg border p-3 flex flex-col gap-2">
          <div class="flex justify-between items-center">
            <div class="text-xs text-gray-500">Example {i + 1}</div>
            <button
              class="btn btn-xs btn-ghost text-error"
              on:click={() => remove_manual_example(i)}
              type="button">Remove</button
            >
          </div>
          <FormElement
            label="Input"
            id="manual_input_{i}"
            inputType="textarea"
            height="base"
            bind:value={example.input}
            optional={true}
            hide_optional_badge={true}
          />
          <FormElement
            label="Output"
            id="manual_output_{i}"
            inputType="textarea"
            height="base"
            bind:value={example.output}
            optional={true}
            hide_optional_badge={true}
          />
        </div>
      {/each}
      <div>
        <button
          class="btn btn-sm btn-outline"
          on:click={add_manual_example}
          type="button">+ Add Example</button
        >
      </div>
    </div>

    <!-- Optional rules (de-emphasized) -->
    <Collapse title="Rules & Constraints" description="Optional">
      <FormElement
        label="Input Requirements"
        description="Optional rules, constraints, and structure for generated task inputs."
        id="requirements"
        inputType="textarea"
        height="medium"
        bind:value={requirements}
        optional={true}
        hide_optional_badge={true}
      />

      <FormElement
        label="Input Examples (text)"
        description="Optional freeform text describing what good inputs look like."
        id="examples"
        inputType="textarea"
        height="base"
        bind:value={examples}
        optional={true}
        hide_optional_badge={true}
      />
    </Collapse>
  </div>

  <slot name="model_selector" />
</FormContainer>

{#if !has_any_example && !requirements.trim()}
  <div class="flex flex-row gap-1 mt-4 justify-end">
    <button
      class="link text-sm text-gray-500"
      disabled={submitting}
      on:click={() => dispatch("generate_without_samples")}
      type="button"
    >
      Generate without examples
    </button>
  </div>
{/if}

<Dialog
  bind:this={preview_dialog}
  title="Preview Example"
  action_buttons={[
    {
      label: "Select",
      isPrimary: true,
      action: () => {
        if (previewing_run) select_run(previewing_run)
        preview_dialog?.close()
        return true
      },
    },
    { label: "Close", isCancel: true },
  ]}
>
  {#if previewing_run}
    <div class="flex flex-col gap-4">
      <div>
        <div class="text-sm font-medium mb-1">Input</div>
        <pre class="whitespace-pre-wrap break-words bg-base-200 p-3 rounded-lg text-sm">{previewing_run.input ?? ""}</pre>
      </div>
      <div>
        <div class="text-sm font-medium mb-1">Output</div>
        <pre class="whitespace-pre-wrap break-words bg-base-200 p-3 rounded-lg text-sm">{previewing_run.output?.output ?? ""}</pre>
      </div>
    </div>
  {/if}
</Dialog>
