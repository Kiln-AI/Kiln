<script lang="ts">
  import { onMount } from "svelte"
  import {
    load_tags,
    tag_store_by_task_id,
    increment_tag as increment_task_tag,
  } from "$lib/stores/tag_store"
  import {
    load_document_tags,
    document_tag_store_by_project_id,
    increment_document_tag,
  } from "$lib/stores/document_tag_store"

  export let project_id: string | null = null
  export let task_id: string | null = null
  export let tag: string | null = null
  export let on_select: (tag: string) => void = () => {}
  export let on_escape: () => void = () => {}
  export let focus_on_mount: boolean = false
  type ExampleTagSet = "task_run" | "doc"
  export let example_tag_set: ExampleTagSet = "task_run"
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
      increment_tag_set(tag)
      on_select(tag)
      error = null
    }
  }

  // Update the in memory set dynamically, as reloading requires full scan of project.
  function increment_tag_set(tag: string) {
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
      case "doc": {
        if (project_id) {
          increment_document_tag(project_id, tag)
        } else {
          console.error(
            "Attempted to increment a tag set for document, but not project_id provided",
          )
        }
        break
      }
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

    switch (example_tag_set) {
      case "task_run": {
        if (!project_id || !task_id) {
          console.error(
            "Requested to load tags for a task, without setting project ID and task ID",
          )
        } else {
          await load_tags(project_id, task_id)
        }
        break
      }
      case "doc": {
        if (!project_id) {
          console.error(
            "Requested to load tags for documents, without setting project ID",
          )
        } else {
          await load_document_tags(project_id)
        }
        break
      }
      default: {
        // typecheck error if we miss a case
        const _: never = example_tag_set
      }
    }
  })

  const DEFAULT_TASK_TAGS = [
    "eval_set",
    "golden",
    "fine_tune_data",
    "needs_rating",
  ]
  const DEFAULT_DOC_TAGS = ["knowledge_base", "faq", "policies", "research"]

  $: task_tag_counts = $tag_store_by_task_id
  $: document_tag_counts = $document_tag_store_by_project_id

  $: sorted_tag_counts = (() => {
    let current_tag_counts: Record<string, number> = {}
    let default_tags: string[] = []

    switch (example_tag_set) {
      case "doc": {
        if (project_id !== null) {
          // fallback here in case the document_tag_counts is still loading
          current_tag_counts = document_tag_counts?.[project_id] ?? {}
        }
        default_tags = DEFAULT_DOC_TAGS
        break
      }
      case "task_run": {
        if (task_id !== null) {
          // fallback here in case the task_tag_counts is still loading
          current_tag_counts = task_tag_counts?.[task_id] ?? {}
        }
        default_tags = DEFAULT_TASK_TAGS
        break
      }
      default: {
        const _: never = example_tag_set
      }
    }

    return sort_tags_by_frequency(current_tag_counts, default_tags)
  })()

  function sort_tags_by_frequency(
    tag_counts: Record<string, number>,
    default_tags: string[],
  ): string[] {
    let sorted_tag_counts: string[] = Object.entries(tag_counts)
      .sort((a, b) => b[1] - a[1])
      .map(([tag, _]) => tag)

    // Add default tags to the bottom of the list, unless they are naturally already in the list
    for (const tag of default_tags) {
      if (!sorted_tag_counts.includes(tag)) {
        sorted_tag_counts.push(tag)
      }
    }

    return sorted_tag_counts
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
      on:click={() => add_tag()}>＋</button
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
