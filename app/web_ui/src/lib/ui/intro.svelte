<script lang="ts">
  export let title: string
  export let description_paragraphs: string[]

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
  <div class="font-medium text-lg text-center">
    {title}
  </div>
  {#each description_paragraphs as paragraph}
    <div>
      {paragraph}
    </div>
  {/each}
  <slot name="description" />
  <div class="flex flex-col gap-4 mt-2">
    {#each action_buttons as button}
      {#if button.href}
        <a
          href={button.href}
          class="btn {button.is_primary ? 'btn-primary' : ''}"
          target={button.new_tab ? "_blank" : "_self"}
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
