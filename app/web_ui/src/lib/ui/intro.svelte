<script lang="ts">
  import MarkdownBlock from "./markdown_block.svelte"

  export let title: string
  export let description_paragraphs: string[] | null = null
  export let description_markdown: string | null = null
  export let align_title_left: boolean = false

  type ActionButton = {
    label: string
    href?: string
    new_tab?: boolean
    onClick?: () => void
    is_primary: boolean
  }

  export let action_buttons: ActionButton[] = []
</script>

<div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
  <div class="flex justify-center items-center">
    <slot name="icon" />
  </div>
  <div
    class="font-medium text-lg {align_title_left ? 'text-left' : 'text-center'}"
  >
    {title}
  </div>
  {#if description_markdown}
    <MarkdownBlock markdown_text={description_markdown} />
  {:else if description_paragraphs}
    {#each description_paragraphs as paragraph}
      <div>
        {paragraph}
      </div>
    {/each}
  {/if}
  <slot name="description" />
  <div class="flex flex-col gap-4 mt-2">
    {#each action_buttons as button}
      {#if button.href}
        <a
          href={button.href}
          class="btn {button.is_primary ? 'btn-primary' : ''}"
          target={button.new_tab ? "_blank" : null}
        >
          {button.label}
        </a>
      {:else if button.onClick}
        <button
          class="btn {button.is_primary ? 'btn-primary' : ''}"
          on:click={button.onClick}
        >
          {button.label}
        </button>
      {/if}
    {/each}
  </div>
</div>
