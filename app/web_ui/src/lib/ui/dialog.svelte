<script lang="ts">
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"

  export let title: string
  export let blur_background: boolean = false
  const id: string = "dialog-" + Math.random().toString(36)
  type ActionButton = {
    label: string
    // both return if the dialog should be closed after the action is performed
    asyncAction?: () => Promise<boolean>
    action?: () => boolean
    isCancel?: boolean
    isPrimary?: boolean
    isError?: boolean
    disabled?: boolean
  }
  export let action_buttons: ActionButton[] = []
  let action_running = false

  let error: KilnError | null = null

  export function show() {
    // Clear the error, so the dialog can be used again
    error = null
    // @ts-expect-error showModal is not a method on HTMLElement
    document.getElementById(id)?.showModal()
  }

  export function close() {
    // @ts-expect-error close is not a method on HTMLElement
    document.getElementById(id)?.close()
  }

  async function perform_button_action(button: ActionButton) {
    let shouldClose = true
    try {
      action_running = true
      // New run, so clear prior errors if any
      error = null
      if (button.asyncAction) {
        shouldClose = await button.asyncAction()
      } else if (button.action) {
        shouldClose = button.action()
      }
    } catch (e) {
      error = createKilnError(e)
      shouldClose = false
    } finally {
      action_running = false
    }

    if (shouldClose) {
      close()
    }
  }
</script>

<dialog {id} class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-medium mb-1">
      {title}
    </h3>
    {#if action_running}
      <div class="flex flex-col items-center justify-center min-h-[100px]">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    {:else}
      <slot />
    {/if}

    {#if error || (action_buttons.length > 0 && !action_running)}
      <div class="flex flex-row gap-2 justify-end mt-6">
        {#if error}
          <form method="dialog">
            <button class="btn btn-sm h-10 btn-outline min-w-24">Close</button>
          </form>
        {:else}
          {#each action_buttons as button}
            {#if button.isCancel}
              <form method="dialog">
                <button class="btn btn-sm h-10 btn-outline min-w-24"
                  >{button.label || "Cancel"}</button
                >
              </form>
            {:else}
              <button
                class="btn btn-sm h-10 min-w-24 {button.isPrimary
                  ? 'btn-primary'
                  : 'btn-secondary'}
                  {button.isError ? 'btn-error' : ''}"
                disabled={button.disabled}
                on:click={() => perform_button_action(button)}
              >
                {button.label || "Confirm"}
              </button>
            {/if}
          {/each}
        {/if}
      </div>
    {/if}
  </div>
  <form
    method="dialog"
    class="modal-backdrop {blur_background ? 'backdrop-blur-sm' : ''}"
  >
    <button>close</button>
  </form>
</dialog>
