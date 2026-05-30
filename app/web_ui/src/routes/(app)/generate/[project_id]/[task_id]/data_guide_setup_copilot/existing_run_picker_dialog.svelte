<script lang="ts">
  // Tag-first existing-run picker for the Kiln Pro Data Guide flow. Select runs
  // by tag (or All); expand the panel to uncheck individual runs. Synthetic
  // runs are excluded — seeding a guide from AI-generated inputs is circular.
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import TagFirstSelector, {
    type TagFirstItem,
  } from "./tag_first_selector.svelte"
  import { fetch_task_sample_candidates } from "$lib/utils/task_sample_example"
  import type { TaskRun } from "$lib/types"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"

  export let project_id: string
  export let task_id: string
  // Run IDs already added; filtered out so the user can't double-add.
  export let existing_task_run_ids: string[] = []

  let dialog: Dialog | null = null
  let selector: TagFirstSelector
  let all_runs: TaskRun[] = []
  let loading = false
  let load_error: KilnError | null = null
  let selected_ids: string[] = []

  const dispatch = createEventDispatcher<{
    add: { runs: TaskRun[] }
  }>()

  export async function show() {
    selected_ids = []
    selector?.reset()
    load_error = null
    dialog?.show()
    if (all_runs.length === 0) {
      await load_runs()
    }
  }

  function close() {
    dialog?.close()
    return true
  }

  async function load_runs() {
    loading = true
    load_error = null
    try {
      const result = await fetch_task_sample_candidates(project_id, task_id)
      all_runs = result.available_runs.filter(
        (r) => r.input_source?.type !== "synthetic",
      )
    } catch (e) {
      load_error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  // Available = not already added (synthetic already excluded in load_runs),
  // newest-first.
  $: available_runs = all_runs
    .filter((r) => !!r.id && !existing_task_run_ids.includes(r.id))
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))

  $: selector_items = available_runs.map(
    (r): TagFirstItem => ({
      id: r.id as string,
      text: r.input ?? "",
      tags: r.tags ?? [],
      date: r.created_at,
    }),
  )

  function handle_add(): boolean {
    if (selected_ids.length === 0) return false
    const id_set = new Set(selected_ids)
    const runs = available_runs.filter((r) => !!r.id && id_set.has(r.id))
    dispatch("add", { runs })
    close()
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  width="wide"
  title="Select from Dataset"
  action_buttons={selected_ids.length > 0
    ? [
        {
          label: `Add ${selected_ids.length} Input${selected_ids.length === 1 ? "" : "s"}`,
          action: () => handle_add(),
          disabled: selected_ids.length === 0,
          isPrimary: true,
        },
      ]
    : []}
>
  <p slot="subtitle" class="text-sm font-light">
    Add examples from your <a
      href={`/dataset/${project_id}/${task_id}`}
      target="_blank"
      rel="noopener"
      class="link">Dataset</a
    > by tag.
  </p>

  {#if loading}
    <div class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg"></span>
    </div>
  {:else if load_error}
    <div class="text-error text-sm">
      Failed to load runs: {load_error.getMessage()}
    </div>
  {:else if available_runs.length === 0}
    <div class="text-sm text-gray-500 py-8 text-center">
      {#if all_runs.length > 0}
        You've already added every eligible run from your dataset.
      {:else}
        No eligible runs available — synthetic (AI-generated) runs can't be used
        as examples.
      {/if}
    </div>
  {:else}
    <TagFirstSelector
      bind:this={selector}
      items={selector_items}
      view_label="View in Dataset"
      view_href={(id) => `/dataset/${project_id}/${task_id}/${id}/run`}
      bind:selected_ids
    />
  {/if}
</Dialog>
