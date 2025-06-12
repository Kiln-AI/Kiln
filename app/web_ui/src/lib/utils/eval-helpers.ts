import type {
  EvalConfig,
  ProviderModels,
  TaskRunConfig,
  EvalResultSummary,
  Eval,
} from "$lib/types"
import { model_name, provider_name_from_id } from "$lib/stores"
import { eval_config_to_ui_name } from "$lib/utils/formatters"
import { string_to_json_key } from "$lib/utils/json_schema_editor/json_schema_templates"

export type UiProperty = {
  name: string
  value: string
}

export function getEvalConfigName(
  evalConfig: EvalConfig,
  modelInfo: ProviderModels | null,
): string {
  const parts = []
  parts.push(eval_config_to_ui_name(evalConfig.config_type))
  parts.push(model_name(evalConfig.model_name, modelInfo))
  return evalConfig.name + " — " + parts.join(", ")
}

export function formatDate(dateString: string | undefined): string {
  if (!dateString) return "Unknown"
  const date = new Date(dateString)
  const datePart = date.toLocaleString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  })
  const timePart = date.toLocaleString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  })
  return `${datePart}\n${timePart}`
}

export function isFinetuneModel(modelName: string | undefined): boolean {
  if (!modelName) return false
  // Finetune IDs are in format: project_id::task_id::finetune_id
  const parts = modelName.split("::")
  return parts.length === 3
}

export function getEnhancedModelName(
  modelNameParam: string | undefined,
  modelInfo: ProviderModels | null,
): string {
  if (!modelNameParam) return "Unknown"
  return model_name(modelNameParam, modelInfo)
}

export function getEnhancedProviderName(
  modelNameParam: string | undefined,
  providerNameParam: string | undefined,
  finetuneBaseModels: Record<string, string>,
): string {
  const baseProvider = provider_name_from_id(providerNameParam || "")

  if (isFinetuneModel(modelNameParam) && modelNameParam) {
    const baseModel = finetuneBaseModels[modelNameParam]
    if (baseModel) {
      return `${baseProvider} (base: ${baseModel})`
    }
  }

  return baseProvider
}

export function getEvalConfigProperties(
  evalConfigId: string | null,
  evalConfigs: EvalConfig[] | null,
  modelInfo: ProviderModels | null,
): UiProperty[] {
  const evalConfig = evalConfigs?.find((config) => config.id === evalConfigId)
  if (!evalConfig) {
    return [
      {
        name: "No Config Selected",
        value: "Select a config from dropdown above",
      },
    ]
  }

  const properties: UiProperty[] = []

  properties.push({
    name: "Algorithm",
    value: eval_config_to_ui_name(evalConfig.config_type),
  })
  properties.push({
    name: "Eval Model",
    value: model_name(evalConfig.model_name, modelInfo),
  })
  properties.push({
    name: "Model Provider",
    value: provider_name_from_id(evalConfig.model_provider),
  })
  return properties
}

export function sortTaskRunConfigs(
  configs: TaskRunConfig[] | null,
  evaluator: Eval | null,
  scoreSummary: EvalResultSummary | null,
  currentSortColumn: "created_at" | "score" | "name" | string | null,
  currentSortDirection: "asc" | "desc",
): TaskRunConfig[] {
  if (!configs || !configs.length) return []

  return [...configs].sort((a, b) => {
    // Default run config always comes first
    if (a.id === evaluator?.current_run_config_id) return -1
    if (b.id === evaluator?.current_run_config_id) return 1

    // If sorting by created_at
    if (currentSortColumn === "created_at") {
      const dateA = a.created_at ? new Date(a.created_at).getTime() : 0
      const dateB = b.created_at ? new Date(b.created_at).getTime() : 0
      return currentSortDirection === "asc" ? dateA - dateB : dateB - dateA
    }

    // If sorting by name
    if (currentSortColumn === "name") {
      return currentSortDirection === "asc"
        ? a.name.localeCompare(b.name)
        : b.name.localeCompare(a.name)
    }

    // If sorting by score (either "score" or a specific score column)
    if (evaluator?.output_scores && scoreSummary?.results) {
      // If currentSortColumn is "score", use the first score column
      const scoreKey =
        currentSortColumn === "score"
          ? evaluator.output_scores.length
            ? string_to_json_key(evaluator.output_scores[0].name)
            : null
          : string_to_json_key(currentSortColumn || "")

      // Skip score-based sorting if no score key is available
      if (!scoreKey) {
        return a.name.localeCompare(b.name)
      }

      const scoreA = scoreSummary.results["" + a.id]?.[scoreKey]?.mean_score
      const scoreB = scoreSummary.results["" + b.id]?.[scoreKey]?.mean_score

      // If both have scores, sort by score
      if (
        scoreA !== null &&
        scoreA !== undefined &&
        scoreB !== null &&
        scoreB !== undefined
      ) {
        return currentSortDirection === "asc"
          ? scoreA - scoreB
          : scoreB - scoreA
      }

      // If only one has a score, it comes first
      if (scoreA !== null && scoreA !== undefined) return -1
      if (scoreB !== null && scoreB !== undefined) return 1
    }

    // Fallback to sort by name while respecting the requested order
    const cmp = a.name.localeCompare(b.name)
    return currentSortDirection === "asc" ? cmp : -cmp
  })
}

export function applyFilters(
  configs: TaskRunConfig[],
  modelFilters: string[],
  finetuneBaseModels: Record<string, string>,
): TaskRunConfig[] {
  if (modelFilters.length === 0) {
    return configs
  }

  return configs.filter((config) => {
    const modelName = config.run_config_properties?.model_name
    if (!modelName) return false

    // Check if the model name itself is in the filters (for base models)
    if (modelFilters.includes(modelName)) return true

    // Check if the base model is in the filters (for finetunes)
    if (isFinetuneModel(modelName)) {
      const baseModel = finetuneBaseModels[modelName]
      return baseModel && modelFilters.includes(baseModel)
    }

    return false
  })
}

export function showIncompleteWarning(
  scoreSummary: EvalResultSummary | null,
): boolean {
  if (!scoreSummary?.run_config_percent_complete) {
    return false
  }

  const values = Object.values(scoreSummary.run_config_percent_complete)
  const minComplete =
    values.length > 0
      ? values.reduce((min, val) => Math.min(min, val), 1.0)
      : 1.0
  return minComplete < 1.0
}

export function getEvalConfigSelectOptions(
  configs: EvalConfig[] | null,
  modelInfo: ProviderModels | null,
): [string, [unknown, string][]][] {
  const configs_options: [string, string][] = []
  for (const c of configs || []) {
    if (c.id) {
      configs_options.push([c.id, getEvalConfigName(c, modelInfo)])
    }
  }

  const results: [string, [unknown, string][]][] = []
  if (configs_options.length > 0) {
    results.push(["Select Eval Method", configs_options])
  }
  results.push(["Manage Eval Methods", [["add_config", "Add Eval Method"]]])
  return results
}

export function getAvailableFilterModels(
  configs: TaskRunConfig[],
  currentFilters: string[],
  finetuneBaseModels: Record<string, string>,
): {
  base_models: Record<string, number>
  finetune_base_models: Record<string, number>
} {
  if (!configs) return { base_models: {}, finetune_base_models: {} }

  const base_models: Record<string, number> = {}
  const finetune_base_models_result: Record<string, number> = {}

  configs.forEach((config) => {
    const modelName = config.run_config_properties?.model_name
    if (!modelName || currentFilters.includes(modelName)) return

    if (isFinetuneModel(modelName)) {
      // For finetunes, group by base model
      const base_model = finetuneBaseModels[modelName]
      if (base_model && !currentFilters.includes(base_model)) {
        const current = finetune_base_models_result[base_model]
        finetune_base_models_result[base_model] = current ? current + 1 : 1
      }
    } else {
      // For regular models, group by model name
      if (!currentFilters.includes(modelName)) {
        const current = base_models[modelName]
        base_models[modelName] = current ? current + 1 : 1
      }
    }
  })

  return { base_models, finetune_base_models: finetune_base_models_result }
}

export async function load_finetune_details(
  task_run_configs: TaskRunConfig[] | null,
  get_finetune_base_model: (model_name: string) => Promise<string | null>,
): Promise<void> {
  if (!task_run_configs) return

  const finetune_models = task_run_configs
    .map((config) => config.run_config_properties?.model_name)
    .filter((model_name) => model_name && isFinetuneModel(model_name))

  await Promise.all(
    finetune_models.map(async (model_name) => {
      if (model_name) {
        await get_finetune_base_model(model_name)
      }
    }),
  )
}
