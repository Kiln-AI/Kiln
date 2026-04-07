import type {
  ExtractorConfig,
  ChunkerConfig,
  ModelProviderName,
} from "$lib/types"
import { client } from "$lib/api_client"
import { createKilnError } from "$lib/utils/error_handlers"
import {
  create_default_extractor_config,
  create_default_chunker_config,
} from "$lib/utils/rag_config_utils"

export type RequiredProvider =
  | "Ollama"
  | "GeminiOrOpenRouter"
  | "OpenaiOrOpenRouter"

type SubConfig = {
  config_name: string
  description: string
}

type ExtractorSubConfig = SubConfig & {
  model_provider_name: ModelProviderName
  model_name: string
}

type DocSkillChunkerSubConfig = SubConfig & {
  chunk_size: number
  chunk_overlap: number
}

export type DocSkillTemplate = {
  name: string
  preview_description: string
  preview_subtitle: string
  preview_tooltip?: string
  required_provider: RequiredProvider
  required_models?: string[]
  required_commands?: string[]
  extractor: ExtractorSubConfig
  chunker: DocSkillChunkerSubConfig
  doc_skill_name: string
  notice_text?: string
  notice_tooltip?: string
}

export const DEFAULT_CONTENT_HEADER =
  "This skill provides access to reference documents. Use the document index to find relevant documents, then load individual document parts as needed."

const gemini_2_5_flash_extractor: ExtractorSubConfig = {
  config_name: "Gemini 2p5 Flash w Default Prompts",
  description: "Gemini 2.5 Flash",
  model_provider_name: "gemini_api",
  model_name: "gemini_2_5_flash",
}

export const doc_skill_templates: Record<string, DocSkillTemplate> = {
  small_context: {
    name: "Small Context",
    preview_subtitle: "Good for small context models.",
    preview_description:
      "Small parts for focused retrieval. Good for structured documents.",
    required_provider: "GeminiOrOpenRouter",
    extractor: gemini_2_5_flash_extractor,
    chunker: {
      config_name: "Fixed Window 1000 - No Overlap",
      description: "Size: 1000, Overlap: 0",
      chunk_size: 1000,
      chunk_overlap: 0,
    },
    doc_skill_name: "Small Context - Gemini Flash",
  },
  medium_context: {
    name: "Medium Context",
    preview_subtitle: "Balanced: fewer loads but uses more context.",
    preview_description: "Balanced parts for general use.",
    required_provider: "GeminiOrOpenRouter",
    extractor: gemini_2_5_flash_extractor,
    chunker: {
      config_name: "Fixed Window 2000 - No Overlap",
      description: "Size: 2000, Overlap: 0",
      chunk_size: 2000,
      chunk_overlap: 0,
    },
    doc_skill_name: "Medium Context - Gemini Flash",
  },
  large_context: {
    name: "Large Context",
    preview_subtitle: "Maximum context retrieval. For large context models.",
    preview_description: "Large parts for maximum context per retrieval.",
    required_provider: "GeminiOrOpenRouter",
    extractor: gemini_2_5_flash_extractor,
    chunker: {
      config_name: "Fixed Window 3000 - No Overlap",
      description: "Size: 3000, Overlap: 0",
      chunk_size: 3000,
      chunk_overlap: 0,
    },
    doc_skill_name: "Large Context - Gemini Flash",
  },
}

const providerOrOpenRouter = (
  settings: Record<string, unknown>,
  provider: ModelProviderName,
): ModelProviderName => {
  switch (provider) {
    case "openai":
      return settings["open_ai_api_key"] ? "openai" : "openrouter"
    case "gemini_api":
      return settings["gemini_api_key"] ? "gemini_api" : "openrouter"
    default:
      return provider
  }
}

export async function build_doc_skill_sub_configs(
  template: DocSkillTemplate,
  project_id: string,
  extractor_configs: ExtractorConfig[],
  chunker_configs: ChunkerConfig[],
): Promise<{
  extractor_config_id: string
  chunker_config_id: string
}> {
  const { data: settings, error: settings_error } =
    await client.GET("/api/settings")
  if (settings_error) {
    throw createKilnError(settings_error)
  }

  let extractor_config_id: string | null = null
  let chunker_config_id: string | null = null

  const extractor_provider = providerOrOpenRouter(
    settings,
    template.extractor.model_provider_name,
  )
  for (const extractor_config of extractor_configs) {
    if (
      extractor_config.name === template.extractor.config_name &&
      extractor_config.id &&
      extractor_config.model_provider_name === extractor_provider
    ) {
      extractor_config_id = extractor_config.id
    }
  }
  if (!extractor_config_id) {
    extractor_config_id = await create_default_extractor_config(
      template.extractor.config_name,
      project_id,
      extractor_provider,
      template.extractor.model_name,
    )
  }
  if (!extractor_config_id) {
    throw new Error(
      `Extractor config not found: ${template.extractor.config_name} (${extractor_provider})`,
    )
  }

  for (const chunker_config of chunker_configs) {
    if (
      chunker_config.name === template.chunker.config_name &&
      chunker_config.id
    ) {
      chunker_config_id = chunker_config.id
    }
  }
  if (!chunker_config_id) {
    chunker_config_id = await create_default_chunker_config(
      template.chunker.config_name,
      project_id,
      template.chunker.chunk_size,
      template.chunker.chunk_overlap,
    )
  }
  if (!chunker_config_id) {
    throw new Error(`Chunker config not found: ${template.chunker.config_name}`)
  }

  return {
    extractor_config_id,
    chunker_config_id,
  }
}
