import type { ModelDetails } from "$lib/types"

/** How an LLM judge scores: plain, with logprobs (G-Eval), or reading the trace with tools. */
export type JudgeAlgorithm = "llm_as_judge" | "g_eval" | "agentic_judge"

type JudgeModelCapabilities = Pick<
  ModelDetails,
  "supports_logprobs" | "supports_function_calling"
>

/** Why each algorithm the model can't run is unavailable, keyed by algorithm. */
export function unsupported_judge_algorithms(
  model: JudgeModelCapabilities,
): Partial<Record<JudgeAlgorithm, string>> {
  const unsupported: Partial<Record<JudgeAlgorithm, string>> = {}
  if (!model.supports_logprobs) {
    unsupported.g_eval =
      "G-Eval requires logprobs which do not work with this model or provider."
  }
  if (!model.supports_function_calling) {
    unsupported.agentic_judge =
      "Agentic Judge requires tool calling, which this model doesn't support."
  }
  return unsupported
}

/** G-Eval when the model has logprobs, otherwise LLM as Judge. Agentic Judge is opt-in. */
export function default_judge_algorithm(
  model: JudgeModelCapabilities,
): JudgeAlgorithm {
  return model.supports_logprobs ? "g_eval" : "llm_as_judge"
}

/** The selection for a model: the user's chosen algorithm while the model supports it, else the default. */
export function judge_algorithm_for_model(
  chosen: JudgeAlgorithm | undefined,
  model: JudgeModelCapabilities,
): JudgeAlgorithm {
  if (chosen && !unsupported_judge_algorithms(model)[chosen]) {
    return chosen
  }
  return default_judge_algorithm(model)
}

/** The LLM judge builder-input flags that select this algorithm on the server. */
export function judge_algorithm_request_flags(algo: JudgeAlgorithm): {
  g_eval: boolean
  trace_tools: boolean
} {
  return {
    g_eval: algo === "g_eval",
    trace_tools: algo === "agentic_judge",
  }
}
