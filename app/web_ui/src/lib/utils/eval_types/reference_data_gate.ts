/**
 * Detect whether a judge config references `reference_data`. Gates the
 * test-before-save requirement, and (for llm_judge) whether the Test Judge pane
 * offers a reference-data input.
 */

/**
 * For llm_judge: returns true when the string `reference_data` appears
 * anywhere in the prompt template.
 *
 * One of the signals `referenceDataUsageMode` uses to decide whether the Test Judge
 * pane offers a reference-data input, whatever SHOW_REFERENCE_DATA_UI is set to. It is
 * the signal for prompts the server derives nothing for — a hand-written one, or one
 * still being edited. What the *saved* judge will require comes from the server
 * instead (`DefaultLlmJudgePromptResponse.reference_keys`), so this test no longer has
 * to be right on its own: a user who edits the reference block out of a default prompt
 * flips this to false while the server keeps requiring the key, and the pane still
 * offers the input.
 *
 * A user-edited prompt is taken at its word — it says `reference_data`, so the pane
 * offers a place to put some. It is a substring test, so a mention inside prose or a
 * Jinja comment counts too; offering an unused input is the harmless direction.
 */
export function uses_reference_data_llm_judge(
  prompt_template: string,
): boolean {
  return prompt_template.includes("reference_data")
}

/**
 * The reference-data keys an llm_judge prompt reads, in first-appearance order.
 *
 * Drives the Test Judge pane's hint for names the server did not declare, so the tester
 * has something to type rather than guessing. Whether a missing one actually skips
 * depends on how the prompt reads it — a bare `{{ reference_data.x }}` raises under
 * StrictUndefined, a `.get("x")` renders around it — so the pane words these as read,
 * not required, and takes required names from the server. Same textual approximation as
 * `uses_reference_data_llm_judge` — it reads Jinja source, not an AST — covering
 * `reference_data.key`, `reference_data["key"]`, and `reference_data.get("key")`.
 */
export function reference_keys_in_llm_judge_prompt(
  prompt_template: string,
): string[] {
  // Dict methods a template may call on `reference_data`. They match as attributes but
  // naming one as a key to type would send the user somewhere wrong.
  const NOT_KEYS = new Set(["get", "items", "keys", "values"])
  // Alternatives in precedence order: `.get("key")` before the bare attribute, so the
  // argument is read as the key rather than `get` itself.
  const pattern =
    /\breference_data\s*(?:\.\s*get\s*\(\s*['"]([^'"]+)['"]|\.\s*([A-Za-z_]\w*)|\[\s*['"]([^'"]+)['"]\s*\])/g

  const keys: string[] = []
  for (const match of prompt_template.matchAll(pattern)) {
    const key = match[1] ?? match[2] ?? match[3]
    if (key && !NOT_KEYS.has(key) && !keys.includes(key)) {
      keys.push(key)
    }
  }
  return keys
}

/**
 * For code_eval: returns true when `reference_data` is used as an identifier
 * in the score function body — excluding:
 *   1. String literals (triple-quoted and single/double-quoted)
 *   2. Python comments (# to end of line)
 *   3. The `def score(...)` parameter list (multi-line safe)
 *
 * This is a deliberate textual approximation rather than AST parsing, per spec.
 */
export function uses_reference_data_code_eval(code: string): boolean {
  let stripped = code

  // 1. Strip string literals including triple-quoted docstrings.
  //    Order: triple-quoted first (greedy within each variant), then single-quoted.
  //    Use [\s\S] for dotAll matching since JS regex . doesn't match \n by default.
  //    Must run before comment stripping so a # inside a string isn't treated
  //    as a comment start.
  stripped = stripped
    .replace(/"""[\s\S]*?"""/g, '""')
    .replace(/'''[\s\S]*?'''/g, "''")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''")

  // 2. Strip Python comments: # to end of line.
  stripped = stripped.replace(/#[^\n]*/g, "")

  // 3. Remove the def score(...) parameter list (multi-line safe).
  //    Match from `def score(` through the closing `)`.
  stripped = stripped.replace(
    /(?:async\s+)?def\s+score\s*\([^)]*\)/g,
    "def score():",
  )

  // 4. Check whether `reference_data` appears as a word-boundary identifier.
  return /\breference_data\b/.test(stripped)
}
