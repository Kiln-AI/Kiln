import type { components } from "./api_schema"

// Project-Input is a variant with path
export type Project = components["schemas"]["Project-Input"]
export type Task = components["schemas"]["Task"]
export type TaskRun = components["schemas"]["TaskRun-Input"]
export type TaskRunOutput = components["schemas"]["TaskRun-Output"]
export type TaskRequirement = components["schemas"]["TaskRequirement"]
export type TaskOutputRating = components["schemas"]["TaskOutputRating-Output"]
export type TaskOutputRatingType = components["schemas"]["TaskOutputRatingType"]
export type RequirementRating = components["schemas"]["RequirementRating"]
export type RatingType = components["schemas"]["TaskOutputRatingType"]
export type AvailableModels = components["schemas"]["AvailableModels"]
export type ProviderModels = components["schemas"]["ProviderModels"]
export type ProviderModel = components["schemas"]["ProviderModel"]
export type ModelDetails = components["schemas"]["ModelDetails"]
export type DatasetSplit = components["schemas"]["DatasetSplit"]
export type Finetune = components["schemas"]["Finetune"]
export type FinetuneProvider = components["schemas"]["FinetuneProvider"]
export type FineTuneParameter = components["schemas"]["FineTuneParameter"]
export type FinetuneWithStatus = components["schemas"]["FinetuneWithStatus"]
export type OllamaConnection = components["schemas"]["OllamaConnection"]
export type DockerModelRunnerConnection =
  components["schemas"]["DockerModelRunnerConnection"]
export type RunSummary = components["schemas"]["RunSummary"]
export type PromptResponse = components["schemas"]["PromptResponse"]
export type ChatStrategy = components["schemas"]["ChatStrategy"]
export type EvalOutputScore = components["schemas"]["EvalOutputScore"]
export type EvalTemplateId = components["schemas"]["EvalTemplateId"]
export type Eval = components["schemas"]["Eval"]
export type EvalConfigType = components["schemas"]["EvalConfigType"]
export type EvalConfig = components["schemas"]["EvalConfig"]
export type TaskRunConfig = components["schemas"]["TaskRunConfig"]
export type RunConfigProperties = components["schemas"]["RunConfigProperties"]
export type EvalResultSummary = components["schemas"]["EvalResultSummary"]
export type EvalRunResult = components["schemas"]["EvalRunResult"]
export type EvalConfigCompareSummary =
  components["schemas"]["EvalConfigCompareSummary"]
export type EvalRun = components["schemas"]["EvalRun"]
export type EvalProgress = components["schemas"]["EvalProgress"]
export type RatingOption = components["schemas"]["RatingOption"]
export type RatingOptionResponse = components["schemas"]["RatingOptionResponse"]
export type FinetuneDatasetInfo = components["schemas"]["FinetuneDatasetInfo"]
export type StructuredOutputMode = components["schemas"]["StructuredOutputMode"]
export type KilnDocument = components["schemas"]["Document"]
export type KilnDocumentKind = components["schemas"]["Kind"]
export type ExtractorConfig = components["schemas"]["ExtractorConfig"]
export type ExtractionSummary = components["schemas"]["ExtractionSummary"]
export type ExtractorType = components["schemas"]["ExtractorType"]
export type OutputFormat = components["schemas"]["OutputFormat"]
export type ExtractionProgress = components["schemas"]["ExtractionProgress"]
export type EmbeddingConfig = components["schemas"]["EmbeddingConfig"]
export type EmbeddingProperties = components["schemas"]["EmbeddingProperties"]
export type EmbeddingModelDetails =
  components["schemas"]["EmbeddingModelDetails"]
export type EmbeddingProvider = components["schemas"]["EmbeddingProvider"]
export type EmbeddingModelName = components["schemas"]["EmbeddingModelName"]
export type ChunkerConfig = components["schemas"]["ChunkerConfig"]
export type ChunkerType = components["schemas"]["ChunkerType"]
export type CreateChunkerConfigRequest =
  components["schemas"]["CreateChunkerConfigRequest"]
export type ModelProviderName = components["schemas"]["ModelProviderName"]
export type RagProgress = components["schemas"]["RagProgress"]
export type RagConfigWithSubConfigs =
  components["schemas"]["RagConfigWithSubConfigs"]
export type VectorStoreConfig = components["schemas"]["VectorStoreConfig"]
export type VectorStoreType = components["schemas"]["VectorStoreType"]
export type LogMessage = components["schemas"]["LogMessage"]
export type BulkCreateDocumentsResponse =
  components["schemas"]["BulkCreateDocumentsResponse"]
export type KilnToolServerDescription =
  components["schemas"]["KilnToolServerDescription"]
export type KilnTaskToolDescription =
  components["schemas"]["KilnTaskToolDescription"]
export type ExternalToolServer = components["schemas"]["ExternalToolServer"]
export type ExternalToolServerApiDescription =
  components["schemas"]["ExternalToolServerApiDescription"]
export type ToolServerType = components["schemas"]["ToolServerType"]
export type ToolSetType = components["schemas"]["ToolSetType"]
export type ToolApiDescription = components["schemas"]["ToolApiDescription"]
export type ToolSetApiDescription =
  components["schemas"]["ToolSetApiDescription"]
export type LocalServerProperties =
  components["schemas"]["LocalServerProperties"]
export type RemoteServerProperties =
  components["schemas"]["RemoteServerProperties"]
export type KilnTaskServerProperties =
  components["schemas"]["KilnTaskServerProperties"]

export type TraceMessage =
  | components["schemas"]["ChatCompletionDeveloperMessageParam"]
  | components["schemas"]["ChatCompletionSystemMessageParam"]
  | components["schemas"]["ChatCompletionUserMessageParam-Input"]
  | components["schemas"]["ChatCompletionAssistantMessageParamWrapper-Input"]
  | components["schemas"]["ChatCompletionToolMessageParamWrapper"]
  | components["schemas"]["ChatCompletionFunctionMessageParam"]
export type Trace = TraceMessage[]
export type ToolCallMessageParam =
  components["schemas"]["ChatCompletionMessageFunctionToolCallParam"]
export type SearchToolApiDescription =
  components["schemas"]["SearchToolApiDescription"]

// Type helpers for ExternalToolServerApiDescription properties

type ToolPropsByType = {
  remote_mcp: RemoteServerProperties
  local_mcp: LocalServerProperties
}

export function toolIsType<T extends keyof ToolPropsByType>(
  x: ExternalToolServerApiDescription,
  t: T,
): asserts x is ExternalToolServerApiDescription & {
  type: T
  properties: ToolPropsByType[T]
} {
  if (x.type !== t) {
    throw new Error(`Tool type mismatch: ${x.type} !== ${t}`)
  }
}

export function isToolType<T extends keyof ToolPropsByType>(
  x: ExternalToolServerApiDescription,
  t: T,
): x is ExternalToolServerApiDescription & {
  type: T
  properties: ToolPropsByType[T]
} {
  // Throw an error if the tool is not of the given type
  toolIsType(x, t)
  return true
}
