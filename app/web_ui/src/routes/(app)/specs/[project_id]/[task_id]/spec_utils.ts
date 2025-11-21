import type { EvalOutputScore } from "$lib/types"

export function specEvalOutputScore(name: string): EvalOutputScore {
  return {
    name: name,
    type: "pass_fail",
    instruction: "Evaluate if the model's behaviour meets the spec.",
  }
}
