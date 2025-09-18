<script lang="ts">
  import { onMount } from "svelte"

  export let tag: string | null = null
  export let on_select: (tag: string) => void = () => {}
  export let on_escape: () => void = () => {}
  export let focus_on_mount: boolean = false
  export let example_tag_set: "task_run" | "doc" = "task_run"
  let example_tags: string[] =
    example_tag_set === "task_run"
      ? ["needs_rating", "golden", "eval_set", "fine_tune_data"]
      : ["knowledge_base", "faq", "policies", "research"]
  let error: string | null = null
  let id = crypto.randomUUID()

  function handle_keyup(event: KeyboardEvent) {
    if (event.key === "Enter") {
      if (tag === null || tag.length === 0) {
        error = "Tags cannot be empty"
      } else if (tag.includes(" ")) {
        error = "Tags cannot contain spaces. Use underscores."
      } else {
        on_select(tag)
        error = null
      }
    } else if (event.key === "Escape") {
      on_escape()
    }
  }

  onMount(() => {
    if (focus_on_mount) {
      document.getElementById(id)?.focus()
    }
  })
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
    {#each example_tags as tag}
      <option value={tag}></option>
    {/each}
  </datalist>
  {#if error}
    <div class="text-error text-sm mt-1">{error}</div>
  {/if}
</div>
