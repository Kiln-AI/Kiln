export function generate_issue_eval_tag(name: string) {
  const tag = name.toLowerCase().replace(/ /g, "_")
  if (tag.length === 0) {
    return "issue_" + (Math.floor(Math.random() * (99999 - 10000 + 1)) + 10000)
  }
  if (tag.length > 32) {
    return tag.slice(0, 32)
  }
  return tag
}
