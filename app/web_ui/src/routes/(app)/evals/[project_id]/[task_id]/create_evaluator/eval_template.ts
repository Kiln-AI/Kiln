import type { EvalOutputScore, EvalTemplateId, EvalDataType } from "$lib/types"
import { generate_eval_tag } from "./eval_utils"

export type EvalTemplateResult = {
  // Server IDs are EvalTemplateId. We have a custom "none" value for the UI.
  template_id: EvalTemplateId | "none"
  name: string
  description: string
  output_scores: EvalOutputScore[]
  default_eval_tag: string
  default_golden_tag: string | null
  template_properties: Record<string, string | number | boolean>
  evaluation_data_type: EvalDataType
}

export function buildReferenceAnswerAccuracyTemplate(): EvalTemplateResult {
  return {
    template_id: "rag",
    name: "Reference Answer Accuracy",
    description:
      "Evaluate how well your task retrieves and answers queries using a Q&A dataset built from your documents.",
    output_scores: [
      {
        name: "Reference Answer Accuracy",
        type: "pass_fail",
        instruction:
          "Evaluate if the model's output is accurate as per the reference answer.",
      },
    ],
    default_eval_tag: "qna_set_" + generate_eval_tag(""),
    default_golden_tag: null,
    template_properties: {},
    evaluation_data_type: "reference_answer",
  }
}
