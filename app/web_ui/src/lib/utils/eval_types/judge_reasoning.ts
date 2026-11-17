/** The judge's written reasoning from an eval run's intermediate outputs, or null when it saved none. */
export function judge_reasoning(
  intermediate_outputs: Record<string, string> | null | undefined,
): string | null {
  return (
    intermediate_outputs?.reasoning ||
    intermediate_outputs?.chain_of_thought ||
    null
  )
}
