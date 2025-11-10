export function generate_eval_tag(name: string): string {
  const tag = name.toLowerCase().replace(/ /g, "_")
  if (tag.length === 0) {
    return "eval_" + (Math.floor(Math.random() * (99999 - 10000 + 1)) + 10000)
  }
  if (tag.length > 32) {
    return tag.slice(0, 32)
  }
  return tag
}
