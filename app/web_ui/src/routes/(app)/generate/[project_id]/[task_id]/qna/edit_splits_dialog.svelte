<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import type { QnaStore } from "./qna_ui_store"
  import { get } from "svelte/store"

  export let qna: QnaStore
  export let show_dialog = false

  let dialog: Dialog | null = null
  let editable_splits: Array<{ tag: string; percent: number }> = []

  export function show() {
    editable_splits = Object.entries(get(qna).splits).map(([tag, percent]) => ({
      tag,
      percent: percent * 100,
    }))
    dialog?.show()
    show_dialog = true
  }

  function add_split() {
    editable_splits = [...editable_splits, { tag: "", percent: 0 }]
  }

  function remove_split(index: number) {
    editable_splits = editable_splits.filter((_, i) => i !== index)
  }

  function get_total_percentage(
    splits: Array<{ tag: string; percent: number }>,
  ): number {
    return splits.reduce((sum, split) => sum + split.percent, 0)
  }

  function is_valid_splits(
    splits: Array<{ tag: string; percent: number }>,
  ): boolean {
    const total = get_total_percentage(splits)
    const has_empty_tags = splits.some((split) => split.tag.trim() === "")
    const has_negative_percent = splits.some((split) => split.percent < 0)

    return (
      (splits.length === 0 || Math.abs(total - 100) < 0.0001) &&
      !has_empty_tags &&
      !has_negative_percent
    )
  }

  function save_splits(): boolean {
    const new_splits: Record<string, number> = {}
    editable_splits.forEach((split) => {
      new_splits[split.tag] = split.percent / 100
    })
    qna.setSplits(new_splits)
    dialog?.close()
    show_dialog = false
    return true
  }

  function cancel_edit(): boolean {
    dialog?.close()
    show_dialog = false
    return true
  }
</script>

<Dialog
  title="Edit Tag Assignments"
  bind:this={dialog}
  action_buttons={[
    {
      label: "Cancel",
      action: cancel_edit,
    },
    {
      label: "Save",
      action: save_splits,
      disabled: !is_valid_splits(editable_splits),
      isPrimary: true,
    },
  ]}
>
  <div class="font-light mb-4 text-sm">
    Tags will be randomly assigned to saved Q&A pairs in the following
    proportions:
  </div>

  {#if editable_splits.length === 0}
    <div class="font-medium my-16 text-center">
      No tags
      <div class="text-gray-500 font-normal text-sm">
        Data will be saved without tags
      </div>
      <button
        on:click={add_split}
        class="btn btn-sm btn-primary btn-outline mx-auto mt-4"
      >
        + Add Tag
      </button>
    </div>
  {:else}
    <div class="space-y-2 mt-12">
      {#each editable_splits as split, index}
        <div class="flex items-center gap-2">
          <input
            type="text"
            bind:value={split.tag}
            placeholder="Tag name"
            class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="number"
            bind:value={split.percent}
            min="0"
            max="100"
            placeholder="0"
            class="w-20 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <span class="text-sm text-gray-500">%</span>
          <button
            on:click={() => remove_split(index)}
            class="px-2 py-1 hover:text-error hover:bg-red-50 rounded"
            title="Remove tag"
          >
            ×
          </button>
        </div>
      {/each}
    </div>

    <div class="flex flex-row items-center mt-3 mb-12">
      <div class="flex-1">
        <button on:click={add_split} class="btn btn-sm btn-primary btn-outline">
          + Add Tag
        </button>
      </div>
      <div class="text-gray-500 text-right">
        Total: {get_total_percentage(editable_splits).toFixed(1)}%
        {#if Math.abs(get_total_percentage(editable_splits) - 100) >= 0.000001}
          <div class="text-sm text-error ml-2">Must total 100%</div>
        {/if}
        {#if editable_splits.some((split) => split.tag === "")}
          <div class="text-sm text-error ml-2">
            Tags must be non-empty strings
          </div>
        {/if}
      </div>
    </div>
  {/if}
</Dialog>
