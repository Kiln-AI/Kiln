<script lang="ts">
  import type { ActionButton } from "../../routes/(app)/types"

  export let buttons: ActionButton[]
</script>

<div class="">
  {#each buttons as button}
    {#if button.href}
      <a
        href={button.href}
        class="btn {button.primary ? 'btn-primary' : ''} {button.notice
          ? 'btn-warning'
          : ''} w-full mt-4"
        class:btn-disabled={button.disabled}
      >
        {button.label}
      </a>
    {:else}
      <button
        class="btn {button.primary ? 'btn-primary' : ''} {button.notice
          ? 'btn-warning'
          : ''} w-full mt-4"
        class:btn-disabled={button.disabled}
        on:click={button.handler}
        disabled={button.disabled}
      >
        {button.label}
      </button>
    {/if}
  {/each}
</div>
