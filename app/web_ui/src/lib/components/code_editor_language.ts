import type { Extension } from "@codemirror/state"

export type CodeEditorLanguage = "python" | "json"

/** Loads only the language package the editor needs. */
export async function load_language_extension(
  language: CodeEditorLanguage,
): Promise<Extension> {
  if (language === "json") {
    const { json } = await import("@codemirror/lang-json")
    return json()
  }
  const { python } = await import("@codemirror/lang-python")
  return python()
}
