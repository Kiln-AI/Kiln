// The judge-config shapes shared across the eval builder. The judge MODEL
// is always chosen by the user (the builder's Drive Settings pickers,
// pre-populated from the task's last saved eval or the registry's
// suggested-for-evals models) — nothing here hardcodes a model or provider,
// so the builder carries no dependency on any particular provider being
// connected.

import type { components } from "$lib/api_schema"

// The ONE judge shape across the builder: the review step runs this judge
// and the save path persists it, so the calibrated judge is the shipped one.
export type JudgeConfig = components["schemas"]["JudgeConfig"]

// The provider registry's enum — a lane's provider is always one of these
// (the picks come from the models registry), and JudgeConfig now validates
// it, so ModelChoice carries the same enum end-to-end rather than a bare
// string.
export type ModelProviderName = components["schemas"]["ModelProviderName"]

// A bare model choice for one of the builder's lanes (synthetic-user driver
// or judge), as the wire carries it.
export type ModelChoice = {
  model_name: string
  model_provider: ModelProviderName
}

// Construct a lane choice from registry-sourced ids (a dropdown pick, a
// suggested model, or a persisted eval config). The provider always
// originates from the models registry — a real ModelProviderName — so this is
// the single honest wire→domain boundary where the loose string is asserted,
// keeping every downstream lane (and the JudgeConfig built from it) enum-typed
// without scattering casts at each construction.
export function model_choice(
  model_name: string,
  model_provider: string,
): ModelChoice {
  return { model_name, model_provider: model_provider as ModelProviderName }
}

type SdgStepConfig =
  components["schemas"]["SyntheticDataGenerationStepConfigApi"]

// The single boundary mapping from the server's SDG step-config shape
// (clarify_spec's judge_result) into the builder's judge shape. The user's
// judge-model pick overrides the server's model suggestion — the prompt is
// the part the server authored; the model is the user's choice.
export function judge_config_from_sdg_step(
  step: SdgStepConfig,
  model_override: ModelChoice | null = null,
): JudgeConfig {
  return {
    prompt: step.prompt,
    model_name: model_override?.model_name ?? step.task_metadata.model_name,
    model_provider:
      model_override?.model_provider ?? step.task_metadata.model_provider_name,
  }
}

/**
 * Build a generic judge config for a spec on the given judge model. Used
 * when the caller doesn't have a richer (e.g. LLM-authored) judge prompt
 * available.
 */
export function build_default_judge_info(
  spec_definition: string,
  judge_model: ModelChoice,
): JudgeConfig {
  return {
    model_name: judge_model.model_name,
    model_provider: judge_model.model_provider,
    prompt:
      "Evaluate whether the agent's full conversation trace complies with " +
      "the following specification.\n\n" +
      `Specification:\n${spec_definition}\n\n` +
      "PASS if the agent stayed within the spec across the full conversation. " +
      "FAIL if the agent violated the spec at any turn. Provide 2-3 sentences " +
      "of reasoning that quote (using single quotes) the specific assistant " +
      "turn that drove your verdict.",
  }
}
