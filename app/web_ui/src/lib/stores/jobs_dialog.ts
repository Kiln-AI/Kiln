import { writable } from "svelte/store"

// Cross-component channel for opening the global jobs dialog. The dialog itself
// is mounted once in (app)/+layout.svelte and subscribes here; any component
// (e.g. the sidebar Jobs widget) can trigger it via `jobs_dialog.open()`.
function createJobsDialog() {
  // Bumped on each open() call. The layout-mounted dialog watches this counter
  // and shows itself whenever it changes, so repeated opens always re-show even
  // if the value of a boolean flag wouldn't have changed.
  const open_signal = writable(0)

  function open() {
    open_signal.update((n) => n + 1)
  }

  return {
    open_signal: { subscribe: open_signal.subscribe },
    open,
  }
}

export const jobs_dialog = createJobsDialog()
