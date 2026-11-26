<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import CodeTrustQuestion from "$lib/components/code_tools/code_trust_question.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { addCodeTrust } from "$lib/api/v2_eval_api"

  export let project_id: string
  export let on_trust_granted: () => void

  let dialog: Dialog
  let trust_error: KilnError | null = null

  export function show() {
    trust_error = null
    dialog.show()
  }

  async function grant_trust_and_proceed(): Promise<boolean> {
    try {
      await addCodeTrust(project_id)
    } catch (e) {
      trust_error = createKilnError(e)
      return false
    }
    on_trust_granted()
    return true
  }
</script>

<Dialog
  bind:this={dialog}
  title="Trust Code and Project?"
  action_buttons={[
    {
      label: "Run — I Trust This Code",
      isWarning: true,
      asyncAction: grant_trust_and_proceed,
    },
  ]}
>
  <CodeTrustQuestion />
  {#if trust_error}
    <div class="mt-3">
      <Warning
        warning_color="error"
        inline={true}
        warning_message={trust_error.getMessage()}
      />
    </div>
  {/if}
</Dialog>
