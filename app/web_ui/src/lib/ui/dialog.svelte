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

  type HeaderButton = {
    image_path: string
    alt_text: string
    action: () => void
  }
  export let header_buttons: HeaderButton[] = []

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
    <div class="flex flex-row gap-2 items-center mb-1">
      <h3 class="grow text-lg font-medium">
        {title}
      </h3>
      {#each header_buttons as button}
        <button
          class="btn btn-sm h-8 w-8 btn-circle btn-ghost focus:outline-none"
          on:click|stopPropagation={button.action}
        >
          <img
            class="h-6 w-6 mb-[1px]"
            src={button.image_path}
            alt={button.alt_text}
          />
        </button>
      {/each}
      <form method="dialog">
        <button
          class="btn btn-sm h-8 w-8 btn-circle btn-ghost focus:outline-none"
          on:click|stopPropagation
        >
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            class="h-6 w-6"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <g clip-path="url(#clip0_429_11083)">
              <path
                d="M7 7.00006L17 17.0001M7 17.0001L17 7.00006"
                stroke="currentColor"
                stroke-width="2.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </g>
            <defs>
              <clipPath id="clip0_429_11083">
                <rect width="24" height="24" fill="white" />
              </clipPath>
            </defs>
          </svg>
        </button>
      </form>
    </div>
    {#if action_running}
      <div class="flex flex-col items-center justify-center min-h-[100px]">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div class="text-error text-sm font-medium">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    {:else}
      <slot />
    {/if}

    {#if error || (action_buttons.length > 0 && !action_running)}
      <div class="flex flex-row gap-2 justify-end mt-6">
        {#if error}
          <form method="dialog">
            <button
              class="btn btn-sm h-10 btn-outline min-w-24"
              on:click|stopPropagation>Close</button
            >
          </form>
        {:else}
          {#each action_buttons as button}
            {#if button.isCancel}
              <form method="dialog">
                <button
                  class="btn btn-sm h-10 btn-outline min-w-24"
                  on:click|stopPropagation>{button.label || "Cancel"}</button
                >
              </form>
            {:else}
              <button
                class="btn btn-sm h-10 min-w-24 {button.isPrimary
                  ? 'btn-primary'
                  : ''}
                  {button.isError ? 'btn-error' : ''}"
                disabled={button.disabled}
                on:click|stopPropagation={() => perform_button_action(button)}
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
