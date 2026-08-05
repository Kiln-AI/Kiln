/**
 * Detect whether a judge config references `reference_data`, which gates
 * the test-before-save requirement.
 */

/**
 * For llm_judge: returns true when the string `reference_data` appears
 * anywhere in the prompt template.
 */
export function uses_reference_data_llm_judge(
  prompt_template: string,
): boolean {
  return prompt_template.includes("reference_data")
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
