import type {
  ExtractorConfig,
  ChunkerConfig,
  EmbeddingConfig,
  VectorStoreConfig,
  VectorStoreType,
  ModelProviderName,
  EmbeddingModelName,
} from "$lib/types"
import { client } from "$lib/api_client"
import {
  default_extractor_document_prompts,
  default_extractor_image_prompts,
  default_extractor_video_prompts,
  default_extractor_audio_prompts,
} from "../../../extractors/[project_id]/create_extractor/default_extractor_prompts"
import { createKilnError } from "$lib/utils/error_handlers"

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
type ChunkerSubConfig = SubConfig & {
  chunk_size: number
  chunk_overlap: number
}
type EmbeddingSubConfig = SubConfig & {
  model_provider_name: ModelProviderName
  model_name: EmbeddingModelName
}
type VectorStoreSubConfig = SubConfig & {
  store_type: VectorStoreType
  top_k: number
}

export type RagConfigTemplate = {
  name: string
  preview_description: string
  preview_subtitle: string
  preview_tooltip?: string
  required_provider: RequiredProvider
  required_models?: string[]
  required_commands?: string[]
  extractor: ExtractorSubConfig
  chunker: ChunkerSubConfig
  embedding: EmbeddingSubConfig
  vector_store: VectorStoreSubConfig
  reranker: null // we can add one later, at this time we just use this to explicitly show that we don't set a reranker
  rag_config_name: string
  notice_text?: string
  notice_tooltip?: string
}

const gemini_2_5_flash_extractor: ExtractorSubConfig = {
  config_name: "Gemini 2p5 Flash w Default Prompts",
  description: "Gemini 2.5 Flash",
  model_provider_name: "gemini_api",
  model_name: "gemini_2_5_flash",
}
const default_chunker: ChunkerSubConfig = {
  config_name: "Size 512 - Overlap 64",
  description: "Size: 512, Overlap: 64",
  chunk_size: 512,
  chunk_overlap: 64,
}
const default_embedding: EmbeddingSubConfig = {
  config_name: "Gemini Embedding 001 (3072 dimensions)",
  description: "Gemini Embedding 001 (3072 dimensions)",
  model_provider_name: "gemini_api",
  model_name: "gemini_embedding_001",
}
const default_vector_store: VectorStoreSubConfig = {
  config_name: "Hybrid Search - Vector and Full-Text",
  description: "Hybrid Search: Vector + Full-Text",
  store_type: "lancedb_hybrid",
  top_k: 10,
}

export const rag_config_templates: Record<string, RagConfigTemplate> = {
  best_quality: {
    name: "Best Quality",
    preview_subtitle: "Spare No Expense",
    preview_description:
      "The best quality search configuration. Uses Gemini 2.5 Pro with hybrid search.",
    preview_tooltip:
      "Gemini 2.5 Pro extraction, Gemini embeddings 001 (3072 dimensions), and LanceDB hybrid search (vector + full-text).",
    required_provider: "GeminiOrOpenRouter",
    extractor: {
      config_name: "Gemini 2p5 Pro w Default Prompts",
      description: "Gemini 2.5 Pro",
      model_provider_name: "gemini_api",
      model_name: "gemini_2_5_pro",
    },
    chunker: default_chunker,
    embedding: default_embedding,
    vector_store: default_vector_store,
    reranker: null,
    rag_config_name: "Best Quality - Gemini Pro Hybrid Search",
  },
  cost_optimized: {
    name: "Cost Optimized",
    preview_subtitle: "Balance Cost and Quality",
    preview_description:
      "Great quality at a lower price. Uses Gemini 2.5 Flash with hybrid search.",
    preview_tooltip:
      "Gemini 2.5 Flash extraction, Gemini embeddings 001 (3072 dimensions), and LanceDB hybrid search (vector + full-text).",
    required_provider: "GeminiOrOpenRouter",
    extractor: gemini_2_5_flash_extractor,
    chunker: default_chunker,
    embedding: default_embedding,
    vector_store: default_vector_store,
    reranker: null,
    rag_config_name: "Cost Optimized - Gemini Flash Hybrid Search",
  },
  local_qwen: {
    name: "All Local",
    preview_subtitle: "Qwen 2.5 VL with Ollama",
    preview_description: "Qwen 2.5 VL on your computer using Ollama.",
    preview_tooltip:
      "Qwen 2.5 VL 7B via Ollama for extraction and Qwen 3 Embedding 0.6B for embeddings.",
    required_provider: "Ollama",
    required_models: ["qwen2.5vl:7b", "qwen3-embedding:0.6b"],
    required_commands: [
      "ollama pull qwen2.5vl:7b",
      "ollama pull qwen3-embedding:0.6b",
    ],
    extractor: {
      config_name: "Qwen 2p5 VL 7B via Ollama",
      description: "Qwen 2.5 VL 7B via Ollama",
      model_provider_name: "ollama",
      model_name: "qwen_2p5_vl_7b",
    },
    chunker: default_chunker,
    embedding: {
      config_name: "Qwen 3 Embedding 0p6B (1024 dimensions)",
      description: "Qwen 3 Embedding 0.6B (1024 dimensions)",
      model_provider_name: "ollama",
      model_name: "qwen_3_embedding_0p6b",
    },
    vector_store: default_vector_store,
    reranker: null,
    rag_config_name: "Ollama - Qwen 2p5 VL",
  },
  vector_only: {
    name: "Vector Only",
    preview_subtitle: "No Full-Text Search",
    preview_description:
      "Use only vector search for semantic similarity, without keyword search.",
    preview_tooltip:
      "Gemini 2.5 Flash extraction, Gemini embeddings 001 (3072 dimensions), and LanceDB vector search (no full-text search).",
    required_provider: "GeminiOrOpenRouter",
    extractor: gemini_2_5_flash_extractor,
    chunker: default_chunker,
    embedding: default_embedding,
    vector_store: {
      config_name: "Vector Search - No Full-Text Search",
      description: "Vector Search",
      store_type: "lancedb_vector",
      top_k: 10,
    },
    reranker: null,
    rag_config_name: "Vector Search - Gemini Flash Vector Search",
  },
  openai_based: {
    name: "OpenAI Based",
    preview_subtitle: "Need to use OpenAI?",
    preview_description:
      "We suggest Gemini, but if you need to use OpenAI try this template.",
    preview_tooltip:
      "GPT-5 extraction, OpenAI Embedding 3 Large (3072 dimensions), and LanceDB hybrid search (vector + full-text).",
    required_provider: "OpenaiOrOpenRouter",
    notice_text: "Does not support audio or video files.",
    notice_tooltip:
      "GPT 5 does not support extracting audio or video files. We suggest using Gemini if you require audio or video support.",
    extractor: {
      config_name: "GPT-5 w Default Prompts",
      description: "GPT-5",
      model_provider_name: "openai",
      model_name: "gpt_5",
    },
    chunker: default_chunker,
    embedding: {
      config_name: "OpenAI Embedding 3 Large",
      description: "OpenAI Embedding 3 Large (3072 dimensions)",
      model_provider_name: "openai",
      model_name: "openai_text_embedding_3_large",
    },
    vector_store: default_vector_store,
    reranker: null,
    rag_config_name: "OpenAI Based - GPT-5 Hybrid Search",
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
      // implement support for other providers here if you need them
      throw new Error(
        `Unsupported provider in providerOrOpenRouter: ${provider}`,
      )
  }
}

export async function build_rag_config_sub_configs(
  template: RagConfigTemplate,
  project_id: string,
  extractor_configs: ExtractorConfig[],
  chunker_configs: ChunkerConfig[],
  embedding_configs: EmbeddingConfig[],
  vector_store_configs: VectorStoreConfig[],
): Promise<{
  extractor_config_id: string
  chunker_config_id: string
  embedding_config_id: string
  vector_store_config_id: string
}> {
  // General design note: matching on name isn't perfect, but assuming people won't make exact name conflicts with the wrong config

  const { data: settings, error: settings_error } =
    await client.GET("/api/settings")
  if (settings_error) {
    throw createKilnError(settings_error)
  }

  let extractor_config_id: string | null = null
  let chunker_config_id: string | null = null
  let embedding_config_id: string | null = null
  let vector_store_config_id: string | null = null

  // Find an existing extractor config with the same name
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

  // Find an existing chunker config with the same name
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

  // Find an existing embedding config with the same name
  const embedding_provider = providerOrOpenRouter(
    settings,
    template.embedding.model_provider_name,
  )
  for (const embedding_config of embedding_configs) {
    if (
      embedding_config.name === template.embedding.config_name &&
      embedding_config.id &&
      embedding_config.model_provider_name === embedding_provider
    ) {
      embedding_config_id = embedding_config.id
    }
  }
  if (!embedding_config_id) {
    embedding_config_id = await create_default_embedding_config(
      template.embedding.config_name,
      project_id,
      embedding_provider,
      template.embedding.model_name,
    )
  }
  if (!embedding_config_id) {
    throw new Error(
      `Embedding config not found: ${template.embedding.config_name} (${embedding_provider})`,
    )
  }

  // Find an existing vector store config with the same name
  for (const vector_store_config of vector_store_configs) {
    if (
      vector_store_config.name === template.vector_store.config_name &&
      vector_store_config.id
    ) {
      vector_store_config_id = vector_store_config.id
    }
  }
  if (!vector_store_config_id) {
    vector_store_config_id = await create_default_vector_store_config(
      template.vector_store.config_name,
      project_id,
      template.vector_store.store_type,
      template.vector_store.top_k,
    )
  }
  if (!vector_store_config_id) {
    throw new Error(
      `Vector store config not found: ${template.vector_store.config_name}`,
    )
  }

  return {
    extractor_config_id,
    chunker_config_id,
    embedding_config_id,
    vector_store_config_id,
  }
}

async function create_default_extractor_config(
  name: string,
  project_id: string,
  provider: ModelProviderName,
  model: string,
): Promise<string> {
  const output_format = "text/markdown"
  const { error: create_extractor_error, data } = await client.POST(
    "/api/projects/{project_id}/create_extractor_config",
    {
      params: {
        path: {
          project_id,
        },
      },
      body: {
        name: name || null,
        model_provider_name: provider,
        model_name: model,
        output_format,
        properties: {
          extractor_type: "litellm",
          prompt_document: default_extractor_document_prompts(output_format),
          prompt_image: default_extractor_image_prompts(output_format),
          prompt_video: default_extractor_video_prompts(output_format),
          prompt_audio: default_extractor_audio_prompts(output_format),
        },
        passthrough_mimetypes: ["text/plain", "text/markdown"],
      },
    },
  )
  if (create_extractor_error) {
    throw create_extractor_error
  }
  if (!data.id) {
    throw new Error("Extractor config not created: missing ID")
  }
  return data.id
}

async function create_default_chunker_config(
  name: string,
  project_id: string,
  chunk_size: number,
  chunk_overlap: number,
): Promise<string> {
  const { error: create_chunker_error, data } = await client.POST(
    "/api/projects/{project_id}/create_chunker_config",
    {
      params: {
        path: {
          project_id,
        },
      },
      body: {
        name: name || null,
        chunker_type: "fixed_window",
        properties: {
          chunker_type: "fixed_window",
          chunk_size: chunk_size,
          chunk_overlap: chunk_overlap,
        },
      },
    },
  )
  if (create_chunker_error) {
    throw create_chunker_error
  }
  if (!data.id) {
    throw new Error("Chunker config not created: missing ID")
  }
  return data.id
}

async function create_default_embedding_config(
  name: string,
  project_id: string,
  model_provider_name: ModelProviderName,
  model_name: EmbeddingModelName,
): Promise<string> {
  const { error: create_embedding_error, data } = await client.POST(
    "/api/projects/{project_id}/create_embedding_config",
    {
      params: {
        path: {
          project_id,
        },
      },
      body: {
        name: name || null,
        model_provider_name: model_provider_name,
        model_name: model_name,
        properties: {},
      },
    },
  )
  if (create_embedding_error) {
    throw create_embedding_error
  }
  if (!data.id) {
    throw new Error("Embedding config not created: missing ID")
  }
  return data.id
}

async function create_default_vector_store_config(
  name: string,
  project_id: string,
  store_type: VectorStoreType,
  top_k: number,
): Promise<string> {
  const { error: create_vector_store_error, data } = await client.POST(
    "/api/projects/{project_id}/create_vector_store_config",
    {
      params: {
        path: {
          project_id,
        },
      },
      body: {
        name: name || null,
        store_type: store_type,
        properties: {
          similarity_top_k: top_k,
        },
      },
    },
  )
  if (create_vector_store_error) {
    throw create_vector_store_error
  }
  if (!data.id) {
    throw new Error("Vector store config not created: missing ID")
  }
  return data.id
}
