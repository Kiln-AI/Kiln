<script lang="ts">
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { createEventDispatcher, onMount } from "svelte"

  const dispatch = createEventDispatcher()

  export let project_id: string
  export let selected_tags: string[] = []

  let available_tags: string[] = []
  let loading_tags = false
  let error: KilnError | null = null

  onMount(async () => {
    await loadAvailableTags()
  })

  async function loadAvailableTags() {
    try {
      loading_tags = true
      error = null

      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/documents/tags",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )

      if (fetch_error) {
        error = createKilnError(fetch_error)
        return
      }

      available_tags = data || []
    } finally {
      loading_tags = false
    }
  }

  function toggleTag(tag: string) {
    if (selected_tags.includes(tag)) {
      selected_tags = selected_tags.filter((t) => t !== tag)
    } else {
      selected_tags = [...selected_tags, tag]
    }
    dispatch("change", { selected_tags })
  }

  function removeTag(tag: string) {
    selected_tags = selected_tags.filter((t) => t !== tag)
    dispatch("change", { selected_tags })
  }

  function clearAllTags() {
    selected_tags = []
    dispatch("change", { selected_tags })
  }

  $: unselected_tags = available_tags.filter(
    (tag) => !selected_tags.includes(tag),
  )
</script>

<div class="flex flex-col gap-4">
  {#if loading_tags}
    <div class="flex items-center gap-2">
      <div class="loading loading-spinner loading-sm"></div>
      <span class="text-sm">Loading tags...</span>
    </div>
  {:else if error}
    <div class="text-error text-sm">{error.message}</div>
  {:else}
    {#if selected_tags.length > 0}
      <div>
        <div class="flex items-center gap-2 mb-2">
          <div class="text-sm font-medium">Selected Tags:</div>
          <button
            class="text-xs text-gray-500 hover:text-gray-700 underline"
            on:click={clearAllTags}
          >
            Clear all
          </button>
        </div>
        <div class="flex flex-row gap-2 flex-wrap">
          {#each selected_tags as tag}
            <div class="badge badge-primary py-3 px-3 max-w-full">
              <span class="truncate">{tag}</span>
              <button
                class="pl-3 font-medium shrink-0 text-white hover:text-gray-200"
                on:click={() => removeTag(tag)}
              >
                ✕
              </button>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if unselected_tags.length > 0}
      <div>
        <div class="text-sm font-medium mb-2">
          {selected_tags.length > 0
            ? "Add more tags:"
            : "Select tags to filter documents:"}
        </div>
        <div class="flex flex-row gap-2 flex-wrap">
          {#each unselected_tags as tag}
            <button
              class="badge bg-gray-200 text-gray-700 py-3 px-3 max-w-full hover:bg-gray-300 transition-colors"
              on:click={() => toggleTag(tag)}
            >
              {tag}
            </button>
          {/each}
        </div>
      </div>
    {:else if selected_tags.length === 0}
      <div class="text-sm text-gray-500">
        No document tags found in this project.
      </div>
    {/if}

    {#if available_tags.length > 0 && selected_tags.length === 0}
      <div class="text-xs text-gray-500">
        Leave empty to include all documents, or select specific tags to only
        include documents with those tags.
      </div>
    {/if}
  {/if}
</div>
