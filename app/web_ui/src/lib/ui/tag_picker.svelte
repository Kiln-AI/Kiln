<script lang="ts">
  import TagDropdown from "./tag_dropdown.svelte"
  import { createEventDispatcher } from "svelte"

  export let tags: string[] = []
  export let tag_type: "doc" | "task_run" = "doc"
  export let project_id: string | null = null
  export let task_id: string | null = null

  const dispatch = createEventDispatcher<{
    tags_changed: { previous: string[]; current: string[] }
  }>()
  export let disabled: boolean = false

  // controls whether the dropdown is initially visible
  // if not then we show the tags with the + button
  export let initial_expanded: boolean = false
  export let show_close_button = true
  export let hide_dropdown_after_select = true

  let show_dropdown = initial_expanded
  let current_tag = ""

  $: show_dropdown = initial_expanded

  function tags_are_equal(tags1: string[], tags2: string[]): boolean {
    return (
      tags1.length === tags2.length && tags1.every((tag) => tags2.includes(tag))
    )
  }

  function emit_tags_changed_if_different(
    previous: string[],
    current: string[],
  ) {
    const deduped_current = [...new Set(current)]
    if (!tags_are_equal(previous, deduped_current)) {
      dispatch("tags_changed", { previous, current: deduped_current })
    }
  }

  function handle_tag_select(tag: string) {
    if (!tags.includes(tag)) {
      const previous_tags = [...tags]
      const new_tags = [...tags, tag]

      emit_tags_changed_if_different(previous_tags, new_tags)
    }
    current_tag = ""
    if (hide_dropdown_after_select) {
      show_dropdown = false
    }
  }

  function handle_escape() {
    if (!initial_expanded) {
      show_dropdown = false
    }
    current_tag = ""
  }

  function handle_remove_tag(tag: string) {
    const previous_tags = [...tags]
    const new_tags = tags.filter((t) => t !== tag)

    emit_tags_changed_if_different(previous_tags, new_tags)
  }

  function toggle_dropdown() {
    if (!disabled) {
      show_dropdown = !show_dropdown
    }
  }

  function handle_close_dropdown() {
    show_dropdown = false
    current_tag = ""
  }
</script>

<div class="w-full">
  <div class="flex flex-row flex-wrap gap-2 mb-2">
    {#each tags.slice().sort() as tag (tag)}
      <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
        <span class="truncate">{tag}</span>
        <button
          class="pl-3 font-medium shrink-0"
          on:click={() => handle_remove_tag(tag)}
          {disabled}>✕</button
        >
      </div>
    {/each}

    {#if !show_dropdown}
      <button
        class="badge bg-gray-200 text-gray-500 p-3 font-medium {disabled
          ? 'opacity-50'
          : ''}"
        on:click={toggle_dropdown}
        {disabled}>＋</button
      >
    {/if}
  </div>

  {#if show_dropdown}
    <div class="flex flex-row gap-2 items-center">
      <TagDropdown
        bind:tag={current_tag}
        {project_id}
        {task_id}
        example_tag_set={tag_type}
        on_select={handle_tag_select}
        on_escape={handle_escape}
        focus_on_mount={true}
      />
      {#if show_close_button}
        <div class="flex-none">
          <button
            class="btn btn-sm btn-circle text-xl font-medium"
            on:click={handle_close_dropdown}>✕</button
          >
        </div>
      {/if}
    </div>
  {/if}
</div>
