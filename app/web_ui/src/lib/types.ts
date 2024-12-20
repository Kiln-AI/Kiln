import type { components } from "./api_schema"

// Project-Input is a variant with path
export type Project = components["schemas"]["Project-Input"]
export type Task = components["schemas"]["Task"]
export type TaskRun = components["schemas"]["TaskRun-Input"]
export type TaskRequirement = components["schemas"]["TaskRequirement"]
export type TaskOutputRating = components["schemas"]["TaskOutputRating-Output"]
export type RequirementRating = components["schemas"]["RequirementRating"]
export type RatingType = components["schemas"]["TaskOutputRatingType"]
export type AvailableModels = components["schemas"]["AvailableModels"]
export type ProviderModels = components["schemas"]["ProviderModels"]
export type DatasetSplit = components["schemas"]["DatasetSplit"]
export type Finetune = components["schemas"]["Finetune"]
export type FinetuneProvider = components["schemas"]["FinetuneProvider"]
export type FineTuneParameter = components["schemas"]["FineTuneParameter"]
export type FinetuneWithStatus = components["schemas"]["FinetuneWithStatus"]
export type OllamaConnection = components["schemas"]["OllamaConnection"]
export type RunSummary = components["schemas"]["RunSummary"]
