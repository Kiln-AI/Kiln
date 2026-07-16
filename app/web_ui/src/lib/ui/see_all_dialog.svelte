<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import Output from "$lib/ui/output.svelte"

  let dialog: Dialog
  let title: string = ""
  let raw: string = ""

  export function show(dialog_title: string, raw_value: string) {
    title = dialog_title
    raw = raw_value
    dialog?.show()
  }
</script>

<Dialog
  bind:this={dialog}
  {title}
  width="wide"
  action_buttons={[{ label: "Close", isCancel: true }]}
>
  <!-- Output renders the full value (JSON gets highlighted) with a copy
       button. No max_height so the dialog shows everything. -->
  <Output raw_output={raw} show_border />
</Dialog>
