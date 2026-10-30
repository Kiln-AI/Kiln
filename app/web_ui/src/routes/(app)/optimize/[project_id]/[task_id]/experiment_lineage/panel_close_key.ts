// A key typed into a field belongs to the field.
const EDITABLE =
  'input, textarea, select, [contenteditable]:not([contenteditable="false"])'

/**
 * Whether a key press anywhere on the page closes the detail panel: an Escape
 * that no other handler has taken, that wasn't typed into a field, and that
 * isn't meant for an open dialog.
 */
export function closes_panel(event: KeyboardEvent): boolean {
  if (event.key !== "Escape" || event.defaultPrevented) {
    return false
  }
  if (event.target instanceof Element && event.target.closest(EDITABLE)) {
    return false
  }
  return document.querySelector("dialog[open]") === null
}
