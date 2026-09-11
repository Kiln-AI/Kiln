/**
 * Escape text for interpolation into markup we assemble ourselves. Anything a user
 * named - an eval score, a run config, a row renamed through the URL - is text, not
 * markup, and the places that build HTML strings by hand have no other guard.
 */
export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}
