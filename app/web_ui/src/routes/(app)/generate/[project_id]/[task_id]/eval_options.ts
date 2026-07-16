import type { Eval, Spec } from "$lib/types"

export type EvalOption = {
  // Display name for the option. Uses the spec name when the eval is backed by
  // a spec, otherwise falls back to the eval's own name (legacy evals).
  name: string
  eval_id: string
}

// Build the list of selectable evals for the "Generate Eval Data" dialog.
//
// Specs are the newer representation of an eval, but legacy evals have no spec.
// If we only listed specs, projects whose evals are all legacy would show an
// empty list. This combines both: specs (preferring the spec name) and any
// legacy evals not referenced by a spec, de-duplicated by eval id.
export function build_eval_options(
  specs: Spec[],
  evals_by_id: Record<string, Eval>,
): EvalOption[] {
  const options: EvalOption[] = []
  const used_eval_ids = new Set<string>()

  for (const spec of specs) {
    if (!spec.eval_id || used_eval_ids.has(spec.eval_id)) {
      continue
    }
    used_eval_ids.add(spec.eval_id)
    options.push({ name: spec.name, eval_id: spec.eval_id })
  }

  for (const eval_item of Object.values(evals_by_id)) {
    if (!eval_item.id || used_eval_ids.has(eval_item.id)) {
      continue
    }
    used_eval_ids.add(eval_item.id)
    options.push({ name: eval_item.name, eval_id: eval_item.id })
  }

  return options
}
