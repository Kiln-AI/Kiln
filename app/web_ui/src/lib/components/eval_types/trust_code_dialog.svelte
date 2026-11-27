<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import CodeTrustQuestion from "$lib/components/code_tools/code_trust_question.svelte"

  // Shared code-trust consent dialog: shown before executing not-yet-saved
  // eval code on the user's machine. on_trust grants trust and retries the
  // pending action; return true to close the dialog.
  export let on_trust: () => Promise<boolean>

  let dialog: Dialog

  export function show() {
    dialog.show()
  }
</script>

<Dialog
  bind:this={dialog}
  title="Trust Code and Project?"
  action_buttons={[
    {
      label: "I Trust this Code",
      isWarning: true,
      asyncAction: on_trust,
    },
  ]}
>
  <CodeTrustQuestion code_label="the eval code" />
</Dialog>
