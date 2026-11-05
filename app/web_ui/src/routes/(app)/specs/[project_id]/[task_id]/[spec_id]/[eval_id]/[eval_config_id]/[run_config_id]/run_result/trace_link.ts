const TRACE_HASH_PREFIX = "#trace-"

export function trace_link_hash(eval_run_id: string): string {
  return TRACE_HASH_PREFIX + encodeURIComponent(eval_run_id)
}

/** The eval run a `#trace-<id>` URL hash points at, or null for any other hash. */
export function eval_run_id_from_trace_hash(hash: string): string | null {
  if (!hash.startsWith(TRACE_HASH_PREFIX)) {
    return null
  }
  const encoded_id = hash.slice(TRACE_HASH_PREFIX.length)
  if (!encoded_id) {
    return null
  }
  try {
    return decodeURIComponent(encoded_id)
  } catch (_) {
    return null
  }
}
