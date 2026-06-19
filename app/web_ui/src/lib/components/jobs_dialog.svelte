<script lang="ts">
  import { get } from "svelte/store"
  import Dialog from "$lib/ui/dialog.svelte"
  import JobsTable from "./jobs_table.svelte"
  import { jobs_dialog } from "$lib/stores/jobs_dialog"
  import { beforeNavigate } from "$app/navigation"

  let dialog: Dialog

  const jobs_dialog_open_signal = jobs_dialog.open_signal

  // Open whenever the cross-component signal changes. Seed from the current
  // value so the dialog stays closed on mount even if the signal has already
  // advanced (e.g. a future conditional remount).
  let last_signal = get(jobs_dialog_open_signal)
  $: if ($jobs_dialog_open_signal !== last_signal) {
    last_signal = $jobs_dialog_open_signal
    dialog?.show()
  }

  // Any client-side navigation (e.g. clicking a back-to-source link inside
  // the table) should close the modal — otherwise it stays overlaid on the
  // destination page. close() on an already-closed dialog is a no-op.
  beforeNavigate(() => {
    dialog?.close()
  })
</script>

<Dialog
  bind:this={dialog}
  title="Jobs"
  width="wide"
  sub_subtitle="View full page →"
  sub_subtitle_link="/jobs"
>
  <JobsTable />
</Dialog>
