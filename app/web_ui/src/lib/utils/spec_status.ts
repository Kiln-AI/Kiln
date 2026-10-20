import type { Eval, Spec, SpecStatus } from "$lib/types"

// Status lives on the eval, falling back to the spec for evals created before that.
export function resolved_status(
  spec: Spec,
  by_id: Map<string, Eval>,
): SpecStatus {
  return (spec.eval_id ? by_id.get(spec.eval_id)?.status : null) ?? spec.status
}
