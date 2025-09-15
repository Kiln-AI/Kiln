<script lang="ts">
  import { onMount } from "svelte"
  import {
    load_tags,
    tag_store_by_task_id,
    increment_tag,
    type TagCounts,
  } from "$lib/stores/tag_store"

  export let project_id: string
  export let task_id: string
  export let tag: string | null = null
  export let on_select: (tag: string) => void = () => {}
  export let on_escape: () => void = () => {}
  export let focus_on_mount: boolean = false
  let error: string | null = null
  let id = crypto.randomUUID()

  function handle_keyup(event: KeyboardEvent) {
    if (event.key === "Enter") {
      if (tag === null || tag.length === 0) {
        error = "Tags cannot be empty"
      } else if (tag.includes(" ")) {
        error = "Tags cannot contain spaces. Use underscores."
      } else {
        increment_tag(task_id, tag)
        on_select(tag)
        error = null
      }
    } else if (event.key === "Escape") {
      on_escape()
    }
  }

  onMount(async () => {
    if (focus_on_mount) {
      document.getElementById(id)?.focus()
    }
    await load_tags(project_id, task_id)
  })

  const DEFAULT_TAGS = ["eval_set", "golden", "fine_tune_data", "needs_rating"]

  $: sorted_tag_counts = get_sorted_tag_counts(
    $tag_store_by_task_id[task_id] || {},
  )

  function get_sorted_tag_counts(tag_counts: TagCounts) {
    let sorted_tag_counts = Object.entries(tag_counts || {})
      .sort((a, b) => b[1] - a[1])
      .map(([tag, _]) => tag)

    // Add default tags to the bottom of the list, unless they are naturally already in the list
    for (const tag of DEFAULT_TAGS) {
      if (!sorted_tag_counts.includes(tag)) {
        sorted_tag_counts.push(tag)
      }
    }

    return sorted_tag_counts
  }
</script>

<div class="w-full">
  <input
    {id}
    list="tag_options"
    type="text"
    class="w-full input input-bordered py-2 {error ? 'input-error' : ''}"
    placeholder="Add a tag"
    bind:value={tag}
    on:keyup={handle_keyup}
  />
  <datalist id="tag_options">
    {#each sorted_tag_counts as tag}
      <option value={tag} />
    {/each}
  </datalist>
  {#if error}
    <div class="text-error text-sm mt-1">{error}</div>
  {/if}
</div>
