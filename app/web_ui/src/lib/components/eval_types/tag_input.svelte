<script lang="ts">
  export let tags: string[] = []
  export let placeholder: string = "Type and press Enter"
  export let disabled: boolean = false
  export let id: string = ""

  tags = [...new Set(tags)]

  let input_value = ""

  function add_tag(raw: string) {
    const value = raw.trim()
    if (value.length === 0) return
    if (!tags.includes(value)) {
      tags = [...tags, value]
    }
    input_value = ""
  }

  function remove_tag(tag: string) {
    tags = tags.filter((t) => t !== tag)
  }

  function handle_keydown(e: KeyboardEvent) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      add_tag(input_value)
    } else if (e.key === "Backspace" && input_value === "" && tags.length > 0) {
      tags = tags.slice(0, -1)
    }
  }

  function handle_paste(e: ClipboardEvent) {
    const text = e.clipboardData?.getData("text") ?? ""
    if (text.includes(",")) {
      e.preventDefault()
      const parts = text.split(",")
      for (const part of parts) {
        add_tag(part)
      }
    }
  }
</script>

<div
  class="flex flex-wrap items-center gap-1.5 p-2 border border-base-300 rounded-lg bg-base-100 min-h-[2.5rem] {disabled
    ? 'opacity-50'
    : ''}"
  role="group"
  aria-label={placeholder || "Tag input"}
  data-testid="tag-input-{id}"
>
  {#each tags as tag (tag)}
    <span class="badge bg-base-200 text-gray-500 gap-1 py-2.5 px-2.5">
      <span class="truncate max-w-[200px]">{tag}</span>
      <button
        type="button"
        class="font-medium text-gray-500 hover:text-gray-700"
        on:click={() => remove_tag(tag)}
        {disabled}
        aria-label="Remove {tag}"
      >
        ✕
      </button>
    </span>
  {/each}
  <input
    type="text"
    {id}
    class="flex-1 min-w-[120px] border-none outline-none bg-transparent text-sm"
    bind:value={input_value}
    on:keydown={handle_keydown}
    on:paste={handle_paste}
    {placeholder}
    {disabled}
    autocomplete="off"
    aria-label={placeholder || "Add item"}
  />
</div>
