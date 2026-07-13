<script lang="ts">
  // Tag-first existing-run picker for the Kiln Pro Data Guide flow. Select runs
  // by tag; the union of the chosen tags is added. Synthetic (AI-generated) runs
  // are allowed, but selecting any surfaces a warning, since a guide is only as
  // realistic as the data it's seeded from.
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import TagFirstSelector, {
    type TagFirstItem,
  } from "./tag_first_selector.svelte"
  import { fetch_task_sample_candidates } from "$lib/utils/task_sample_example"
  import type { TaskRun } from "$lib/types"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import Intro from "$lib/ui/intro.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import DatabaseIcon from "$lib/ui/icons/database_icon.svelte"

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
      // Synthetic runs are included; selecting one surfaces a warning below
      // rather than being hidden.
      all_runs = result.available_runs
    } catch (e) {
      load_error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  // Available = not already added, newest-first.
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

  // Warn when any selected run (pulled in via a chosen tag) is AI-generated.
  $: selected_id_set = new Set(selected_ids)
  $: has_synthetic_selected = available_runs.some(
    (r) =>
      !!r.id &&
      selected_id_set.has(r.id) &&
      r.input_source?.type === "synthetic",
  )

  // The picker is tag-first, so untagged runs can't be selected here. When no
  // available run is tagged we show an empty state nudging the user to tag (or
  // create) runs instead of rendering an empty table.
  $: has_tagged_runs = available_runs.some((r) => !!r.tags && r.tags.length > 0)
  // Whether the dataset has any tagged eligible runs at all (before filtering
  // out already-added ones) — lets the empty state say "you've added them all".
  $: dataset_has_tagged = all_runs.some((r) => !!r.tags && r.tags.length > 0)
  $: all_added = available_runs.length === 0 && all_runs.length > 0

  // Empty-state copy, by reason. The action always links to the Dataset so the
  // user can learn how to create/tag runs there.
  $: empty_state =
    available_runs.length === 0
      ? all_added
        ? {
            title: "All Runs Added",
            description:
              "You've already added every eligible run from your dataset. Run your task to create more, then add them here.",
          }
        : {
            title: "No Runs To Add",
            description:
              "Your dataset has no eligible runs yet. Run your task to create some, then add them here.",
          }
      : dataset_has_tagged
        ? {
            title: "No Tagged Runs To Add",
            description:
              "You've already added all of your tagged runs. Tag more runs in your Dataset to add them here.",
          }
        : {
            title: "No Tagged Runs To Add",
            description:
              "Only tagged runs can be added here. Add tags to runs in your Dataset, then add them here.",
          }

  // The dialog loads its run list once on open and doesn't live-refresh, so
  // close it after sending the user to the Dataset (mirrors the library dialog).
  function go_to_dataset() {
    window.open(`/dataset/${project_id}/${task_id}`, "_blank", "noopener")
    close()
  }

  function handle_add(): boolean {
    if (selected_ids.length === 0) return false
    const id_set = new Set(selected_ids)
    const runs = available_runs.filter((r) => !!r.id && id_set.has(r.id))
    dispatch("add", { runs })
    close()
    return true
  }

  function dataset_tags_href(tags: string[]): string {
    const params = new URLSearchParams()
    tags.forEach((t) => params.append("tags", t))
    return `/dataset/${project_id}/${task_id}?${params.toString()}`
  }
</script>

<Dialog
  bind:this={dialog}
  width="wide"
  title="Select from Dataset"
  action_buttons={has_tagged_runs
    ? [
        {
          label: "Add",
          action: () => handle_add(),
          disabled: selected_ids.length === 0,
          isPrimary: true,
        },
      ]
    : []}
>
  <p slot="subtitle" class="text-sm font-light">
    Select tags to add every matching example from your <a
      href={`/dataset/${project_id}/${task_id}`}
      target="_blank"
      rel="noopener"
      class="link">Dataset</a
    >.
  </p>

  {#if loading}
    <div class="flex justify-center py-12">
      <span class="loading loading-spinner loading-lg"></span>
    </div>
  {:else if load_error}
    <div class="text-error text-sm">
      Failed to load runs: {load_error.getMessage()}
    </div>
  {:else if !has_tagged_runs}
    <!-- Empty state: no eligible runs, all already added, or runs exist but
         none are tagged (untagged runs can't be picked tag-first). -->
    <div class="py-8 flex justify-center">
      <Intro
        title={empty_state.title}
        description_paragraphs={[empty_state.description]}
        action_buttons={[
          {
            label: "Go to Dataset",
            onClick: go_to_dataset,
            is_primary: true,
          },
        ]}
      >
        <div slot="icon" class="h-12 w-12">
          <DatabaseIcon />
        </div>
      </Intro>
    </div>
  {:else}
    <TagFirstSelector
      bind:this={selector}
      items={selector_items}
      count_header="Runs"
      unit_singular="run"
      unit_plural="runs"
      filtered_href={dataset_tags_href}
      bind:selected_ids
    />
    {#if has_synthetic_selected}
      <div class="mt-4">
        <Warning
          warning_message="Some selected examples are synthetic. Inputs generated from a Data Guide are only as realistic as the examples it's built from, so real data works best."
          warning_color="warning"
          warning_icon="exclaim"
        />
      </div>
    {/if}
  {/if}
</Dialog>
