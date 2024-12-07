<script lang="ts">
  import { goto } from "$app/navigation"

  export let title: string = ""
  export let subtitle: string = ""
  export let sub_subtitle: string = ""

  type ActionButton = {
    label: string
    handler?: () => void
    href?: string
    primary?: boolean
  }

  export let action_buttons: ActionButton[] = []

  function run_action_button(action_button: ActionButton) {
    if (action_button.handler) {
      action_button.handler()
    } else if (action_button.href) {
      goto(action_button.href)
    }
  }
</script>

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
          class="btn btn-xs md:btn-md md:px-6 {action_button.primary
            ? 'btn-primary'
            : ''}"
        >
          {action_button.label}
        </button>
      </div>
    {/each}
  </div>
</div>

<div class="mt-8 mb-12">
  <slot />
</div>
