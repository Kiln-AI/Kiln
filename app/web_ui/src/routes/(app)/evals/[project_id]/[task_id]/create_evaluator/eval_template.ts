import type { EvalOutputScore, EvalTemplateId, EvalDataType } from "$lib/types"

export type EvalTemplateResult = {
  // Server IDs are EvalTemplateId. We have a custom "none" value for the UI.
  template_id: EvalTemplateId | "none"
  name: string
  description: string
  output_scores: EvalOutputScore[]
  default_eval_tag: string
  default_golden_tag: string
  template_properties: Record<string, string | number | boolean>
  evaluation_data_type: EvalDataType
}
