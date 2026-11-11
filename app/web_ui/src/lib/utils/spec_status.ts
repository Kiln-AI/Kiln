import type { Eval, Spec, SpecStatus } from "$lib/types"

// An eval holds its own status. Older evals have none, and their spec holds it.
export function resolved_status(
  spec: Spec,
  by_id: Map<string, Eval>,
): SpecStatus {
  return (spec.eval_id ? by_id.get(spec.eval_id)?.status : null) ?? spec.status
}
