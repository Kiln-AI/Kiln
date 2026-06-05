// Defaults for the LLM-as-judge config when the user doesn't pick one
// explicitly. Lives here (not in a route file) so studio_server, future
// CLI tooling, and any other consumer can share the same defaults.
//
// Model choice rationale: gpt_4o via openrouter is broadly available, a
// solid baseline judge, and the user is likely to already have an
// openrouter key configured if they were able to run a multi-turn task
// at all (the synthetic-user driver hits openrouter too).
//
// When kiln_server adds a "generate judge config" endpoint OR the UI
// gains a judge-model picker, both should fall back to these defaults.
//
// Steve's constraint (server-generated judge configs can't use the
// user's local/custom models) means this kind of default belongs on the
// client side of the network boundary, not kiln_server.

import type { SyntheticDataGenerationStepConfigApi } from "$lib/types"

export const DEFAULT_JUDGE_MODEL_NAME = "gpt_4o"
export const DEFAULT_JUDGE_MODEL_PROVIDER = "openrouter"

/**
 * Build a generic judge config for a spec. Used when the caller doesn't
 * have a richer (e.g. LLM-authored) judge prompt available.
 */
export function build_default_judge_info(
  spec_definition: string,
): SyntheticDataGenerationStepConfigApi {
  return {
    task_metadata: {
      model_name: DEFAULT_JUDGE_MODEL_NAME,
      model_provider_name: DEFAULT_JUDGE_MODEL_PROVIDER,
    },
    prompt:
      "Evaluate whether the agent's full conversation trace complies with " +
      "the following specification.\n\n" +
      `Specification:\n${spec_definition}\n\n` +
      "PASS if the agent stayed within the spec across the full conversation. " +
      "FAIL if the agent violated the spec at any turn. Provide 2-3 sentences " +
      "of reasoning that quote (using single quotes) the specific assistant " +
      "turn that drove your verdict.",
  } as SyntheticDataGenerationStepConfigApi
}
