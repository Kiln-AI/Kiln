<script lang="ts">
  import { goto } from "$app/navigation"
  import type { ActionButton } from "./types"

  export let title: string = ""
  export let subtitle: string = ""
  export let sub_subtitle: string = ""

  export let action_buttons: ActionButton[] = []

  function run_action_button(action_button: ActionButton) {
    if (action_button.handler) {
      action_button.handler()
    } else if (action_button.href) {
      goto(action_button.href)
    }
  }

  function handle_key_down(event: KeyboardEvent) {
    // Skip if any input element is focused
    if (
      document.activeElement instanceof HTMLInputElement ||
      document.activeElement instanceof HTMLTextAreaElement ||
      document.activeElement instanceof HTMLSelectElement
    ) {
      return
    }

    for (const action_button of action_buttons) {
      if (event.key === action_button.shortcut) {
        event.preventDefault()
        run_action_button(action_button)
        return
      }
    }
  }
</script>

<svelte:window on:keydown={handle_key_down} />

<div class="flex flex-row">
  <div class="flex flex-col grow">
    <h1 class="text-2xl font-bold">{title}</h1>
    {#if subtitle}
      <p class="text-base font-medium mt-1">{subtitle}</p>
    {/if}
    {#if sub_subtitle}
      <p class="text-sm font-light mt-1">{sub_subtitle}</p>
    {/if}
  </div>
  <div class="flex flex-col md:flex-row gap-2">
    {#each action_buttons as action_button}
      <div>
        <button
          on:click={() => run_action_button(action_button)}
          class="btn btn-xs md:btn-md {!action_button.icon
            ? 'md:px-6'
            : ''} {action_button.primary ? 'btn-primary' : ''}"
          disabled={action_button.disabled ?? false}
        >
          {#if action_button.notice}
            <span class="bg-primary rounded-full w-3 h-3 mr-1" />
          {/if}
          {action_button.label || ""}
          {#if action_button.icon}
            <img
              alt={action_button.label || ""}
              src={action_button.icon}
              class="w-6 h-6"
            />
          {/if}
        </button>
      </div>
    {/each}
  </div>
</div>

<div class="mt-8 mb-12">
  <slot />
</div>
