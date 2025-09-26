<script lang="ts">
  import { onMount } from "svelte"
  import {
    load_tags,
    tag_store_by_task_id,
    increment_tag as increment_task_tag,
    type TagCounts,
  } from "$lib/stores/tag_store"

  export let project_id: string | null = null
  export let task_id: string | null = null
  export let tag: string | null = null
  export let on_select: (tag: string) => void = () => {}
  export let on_escape: () => void = () => {}
  export let focus_on_mount: boolean = false
  export let example_tag_set: "task_run" | "doc" = "task_run"
  let error: string | null = null
  let id = crypto.randomUUID()
  let datalist_id = `${id}_options`

  function handle_keyup(event: KeyboardEvent) {
    if (event.key === "Enter") {
      add_tag()
    } else if (event.key === "Escape") {
      on_escape()
    }
  }

  function add_tag() {
    if (tag === null || tag.length === 0) {
      error = "Tags cannot be empty"
    } else if (tag.includes(" ")) {
      error = "Tags cannot contain spaces. Use underscores."
    } else {
      increment_tag_set(task_id, tag)
      on_select(tag)
      error = null
    }
  }

  // Update the in memory set dynamically, as reloading requires full scan of project.
  function increment_tag_set(task_id: string | null, tag: string) {
    switch (example_tag_set) {
      case "task_run": {
        if (task_id) {
          increment_task_tag(task_id, tag)
        } else {
          console.error(
            "Attempted to increment a tag set for task, but not task_id provided",
          )
        }
        break
      }
      case "doc":
        // No tracking yet
        break
      default: {
        // Check we don't miss a new case
        const _: never = example_tag_set
      }
    }
  }

  onMount(async () => {
    if (focus_on_mount) {
      document.getElementById(id)?.focus()
    }
    // Load task tasks, if we're rendering task tags
    if (example_tag_set === "task_run") {
      if (!project_id || !task_id) {
        console.error(
          "Requested to load tags for a task, without setting project ID and task ID",
        )
      } else {
        await load_tags(project_id, task_id)
      }
    }
  })

  const DEFAULT_TAGS = ["eval_set", "golden", "fine_tune_data", "needs_rating"]

  $: sorted_tag_counts = get_sorted_tag_counts($tag_store_by_task_id, task_id)

  function get_sorted_tag_counts(
    task_tag_connts: Record<string, TagCounts>,
    task_id: string | null,
  ): string[] {
    switch (example_tag_set) {
      case "doc":
        // Hard coded sample tags for doc library
        return ["knowledge_base", "faq", "policies", "research"]
      case "task_run": {
        let sorted_tag_counts: string[] = []
        if (task_id === null) {
          console.error(
            "task_id is null, but example_tag_set is task_run. Can't load the task tags.",
          )
        } else {
          const tag_counts = task_tag_connts[task_id]
          sorted_tag_counts = Object.entries(tag_counts || {})
            .sort((a, b) => b[1] - a[1])
            .map(([tag, _]) => tag)
        }

        // Add default tags to the bottom of the list, unless they are naturally already in the list
        for (const tag of DEFAULT_TAGS) {
          if (!sorted_tag_counts.includes(tag)) {
            sorted_tag_counts.push(tag)
          }
        }

        return sorted_tag_counts
      }
      default: {
        // Compiler check we never miss a case
        const _: never = example_tag_set
        return []
      }
    }
  }
</script>

<div class="w-full">
  <div class="flex flex-row gap-2 items-center">
    <input
      {id}
      list={datalist_id}
      type="text"
      autocomplete="off"
      autocapitalize="none"
      spellcheck="false"
      class="w-full input input-bordered py-2 {error ? 'input-error' : ''}"
      placeholder="Add a tag"
      bind:value={tag}
      on:keyup={handle_keyup}
    />
    <button
      class="btn btn-sm {tag && tag.length > 0
        ? 'btn-primary'
        : 'btn-disabled'} btn-circle text-xl font-medium"
      on:click={() => add_tag()}>+</button
    >
  </div>
  <datalist id={datalist_id}>
    {#each sorted_tag_counts as tag}
      <option value={tag} />
    {/each}
  </datalist>
  {#if error}
    <div class="text-error text-sm mt-1">{error}</div>
  {/if}
</div>
