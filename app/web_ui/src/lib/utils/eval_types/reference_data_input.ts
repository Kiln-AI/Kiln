/**
 * Parsing for the Test Judge pane's advanced reference-data input, shared by
 * the add-judge builder and the eval creation form.
 */

export type ReferenceDataParseResult =
  | { ok: true; data: Record<string, unknown> | null }
  | { ok: false; error: string }

/**
 * Parse the reference-data textarea into the object sent as
 * eval_input.reference_data. Blank input is valid (no reference data);
 * anything else must be a JSON object.
 */
export function parse_reference_data(data: string): ReferenceDataParseResult {
  if (!data.trim()) {
    return { ok: true, data: null }
  }
  try {
    const parsed = JSON.parse(data.trim())
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      Array.isArray(parsed)
    ) {
      return {
        ok: false,
        error:
          "Reference data must be a JSON object (not null, array, string, or number).",
      }
    }
    return { ok: true, data: parsed }
  } catch {
    return { ok: false, error: "Reference data must be valid JSON (object)." }
  }
}

/**
 * The top-level keys of the reference-data object, for the reference-key
 * dropdowns. Invalid or non-object input yields no keys.
 */
export function parse_reference_keys(data: string): string[] {
  const result = parse_reference_data(data)
  return result.ok && result.data ? Object.keys(result.data) : []
}
