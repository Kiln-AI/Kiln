import type { EvalOutputScore } from "$lib/types"
import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"

/**
 * Validate a test run's returned scores against the eval's declared scores.
 *
 * Both missing and unexpected keys invalidate the run: extra keys usually
 * mean a stale key was left behind (e.g. the code judge's
 * "score_name_placeholder" alongside the real key), which would fail score
 * validation on a real eval run.
 */
export function validate_result_shape(
  scores: Record<string, number> | undefined,
  output_scores: EvalOutputScore[] | undefined,
): { valid: boolean; message: string | null } {
  if (!scores || !output_scores?.length) {
    return { valid: true, message: null }
  }

  const expected_keys = output_scores.map((s) => string_to_json_key(s.name))
  const returned_keys = Object.keys(scores)
  const missing = expected_keys.filter((k) => !returned_keys.includes(k))
  const extra = returned_keys.filter((k) => !expected_keys.includes(k))

  if (missing.length === 0 && extra.length === 0) {
    return { valid: true, message: null }
  }

  const parts: string[] = []
  if (missing.length > 0) {
    parts.push(
      `Missing expected scores: ${missing.join(", ")}. The eval returned: ${returned_keys.join(", ") || "(none)"}`,
    )
  }
  if (extra.length > 0) {
    parts.push(`Unexpected scores: ${extra.join(", ")}`)
  }
  return { valid: false, message: parts.join(" ") }
}
