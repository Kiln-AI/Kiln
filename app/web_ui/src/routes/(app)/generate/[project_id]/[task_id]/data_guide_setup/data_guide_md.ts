// Compose a DataGuide's two persisted bodies into a single markdown blob with
// the canonical `# Reference Examples` / `# Guidelines & Rules` headings.
// Mirrors the backend `_compose_guide_md` so previews look identical to what
// the runtime sees.
export function compose_guide_md(
  examples_md: string,
  rules_md: string,
): string {
  const parts: string[] = []
  if (examples_md.trim()) {
    parts.push(`# Reference Examples\n\n${examples_md.trim()}`)
  }
  if (rules_md.trim()) {
    parts.push(`# Guidelines & Rules\n\n${rules_md.trim()}`)
  }
  return parts.join("\n\n")
}
