<script lang="ts">
  import Dialog from "./dialog.svelte"
  import { createKilnError } from "$lib/utils/error_handlers"
  import { base_url } from "$lib/api_client"
  import Warning from "./warning.svelte"
  import { _ } from "svelte-i18n"

  export let name: string
  export let delete_url: string
  export let delete_message: string | undefined = undefined
  export let after_delete: () => void = () => {
    // The parent page can override this, but reload the page by default
    window.location.reload()
  }

  async function delete_item(): Promise<boolean> {
    try {
      const response = await fetch(base_url + delete_url, {
        method: "DELETE",
      })
      if (!response.ok) {
        let error_body: unknown
        try {
          error_body = await response.json()
        } catch (e) {
          throw new Error($_("dialog.failed_to_delete"))
        }
        throw createKilnError(error_body)
      }
      after_delete()
      return true
    } catch (e) {
      throw createKilnError(e)
    }
  }

  let dialog: Dialog | null = null
  export function show() {
    dialog?.show()
  }
</script>

<Dialog
  title={$_("dialog.delete_title", { values: { name } })}
  bind:this={dialog}
  action_buttons={[
    {
      label: $_("common.delete"),
      asyncAction: delete_item,
      isError: true,
    },
  ]}
>
  <div class="mt-6 flex flex-col gap-4">
    {#if delete_message}
      <p>{delete_message}</p>
    {:else}
      <p>
        {$_("dialog.delete_confirm_message", { values: { name } })}
      </p>
    {/if}
    <Warning warning_message={$_("dialog.delete_warning")} />
  </div>
</Dialog>
