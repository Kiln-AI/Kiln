const LINKED_DIALOGS = ["trace", "reasoning"] as const

/** The per-row dialogs a URL hash can open on the results page. */
export type LinkedDialog = (typeof LINKED_DIALOGS)[number]

export type DialogLink = { dialog: LinkedDialog; eval_run_id: string }

export function dialog_link_hash({ dialog, eval_run_id }: DialogLink): string {
  return `#${dialog}-${encodeURIComponent(eval_run_id)}`
}

/** The row dialog a `#<dialog>-<eval run id>` URL hash points at, or null for any other hash. */
export function dialog_link_from_hash(hash: string): DialogLink | null {
  for (const dialog of LINKED_DIALOGS) {
    const prefix = `#${dialog}-`
    if (!hash.startsWith(prefix)) {
      continue
    }
    const encoded_id = hash.slice(prefix.length)
    if (!encoded_id) {
      return null
    }
    try {
      return { dialog, eval_run_id: decodeURIComponent(encoded_id) }
    } catch (_) {
      return null
    }
  }
  return null
}
