import type { ErrorWithTrace } from "$lib/types"

// Type guard that checks whether an unknown fetch-error body matches the
// structured ErrorWithTrace shape returned by the /run endpoint on an
// adapter-level failure. Plain HTTPException bodies (shape {detail: "..."})
// and unparseable responses return false, letting the caller fall back to
// the existing error-display path.
export function looks_like_error_with_trace(
  body: unknown,
): body is ErrorWithTrace {
  if (body === null || typeof body !== "object") {
    return false
  }
  const candidate = body as Record<string, unknown>
  if (typeof candidate.message !== "string") {
    return false
  }
  if (typeof candidate.error_type !== "string") {
    return false
  }
  const trace = candidate.trace
  if (trace !== null && trace !== undefined && !Array.isArray(trace)) {
    return false
  }
  return true
}
