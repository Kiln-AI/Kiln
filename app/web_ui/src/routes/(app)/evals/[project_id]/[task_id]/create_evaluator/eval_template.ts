import type { EvalOutputScore, EvalTemplateId } from "$lib/types"

export type EvalTemplateResult = {
  // Server IDs are EvalTemplateId. We have a custom "none" value for the UI.
  template_id: EvalTemplateId | "none"
  name: string
  description: string
  output_scores: EvalOutputScore[]
}
