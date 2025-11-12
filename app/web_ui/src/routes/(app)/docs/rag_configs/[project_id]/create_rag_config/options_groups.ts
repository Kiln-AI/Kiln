import {
  embedding_model_name,
  get_model_friendly_name,
  provider_name_from_id,
} from "$lib/stores"
import type {
  ChunkerConfig,
  EmbeddingConfig,
  ExtractorConfig,
  RerankerConfig,
  VectorStoreConfig,
} from "$lib/types"
import type { OptionGroup } from "$lib/ui/fancy_select_types"
import {
  extractor_output_format,
  format_chunker_config_overview,
} from "$lib/utils/formatters"

function fmt_extractor_label(extractor: ExtractorConfig) {
  return `${get_model_friendly_name(extractor.model_name)} (${provider_name_from_id(extractor.model_provider_name)}) • ${extractor_output_format(extractor.output_format)}`
}

export function build_extractor_options(extractor_configs: ExtractorConfig[]) {
  return [
    {
      options: [
        {
          label: "New Extractor Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },
    ...(extractor_configs.length > 0
      ? [
          {
            label: "Extractors",
            options: extractor_configs
              .filter((config) => !config.is_archived)
              .map((config) => ({
                label: fmt_extractor_label(config),
                value: config.id,
                description:
                  config.name +
                  (config.description ? " - " + config.description : ""),
              })),
          },
        ]
      : []),
  ] as OptionGroup[]
}

export function build_chunker_options(chunker_configs: ChunkerConfig[]) {
  return [
    {
      options: [
        {
          label: "New Chunker Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },
    ...(chunker_configs.length > 0
      ? [
          {
            label: "Chunkers",
            options: chunker_configs.map((config) => {
              return {
                label: format_chunker_config_overview(config),
                value: config.id,
                description:
                  config.name +
                  (config.description ? ` • ${config.description}` : ""),
              }
            }),
          },
        ]
      : []),
  ] as OptionGroup[]
}

function fmt_embedding_label(config: EmbeddingConfig) {
  return (
    `${embedding_model_name(config.model_name, config.model_provider_name)} (${provider_name_from_id(config.model_provider_name)})` +
    (config.properties?.dimensions
      ? `• ${config.properties?.dimensions} dimensions`
      : "")
  )
}

export function build_embedding_options(embedding_configs: EmbeddingConfig[]) {
  return [
    {
      options: [
        {
          label: "New Embedding Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },
    ...(embedding_configs.length > 0
      ? [
          {
            label: "Embedding Models",
            options: embedding_configs.map((config) => ({
              label: fmt_embedding_label(config),
              value: config.id,
              description:
                config.name +
                (config.description ? " • " + config.description : ""),
            })),
          },
        ]
      : []),
  ] as OptionGroup[]
}

function fmt_vector_store_label(config: VectorStoreConfig) {
  switch (config.store_type) {
    case "lancedb_fts":
      return "Full Text Search"
    case "lancedb_vector":
      return "Vector Search"
    case "lancedb_hybrid":
      return "Hybrid Search"
    default: {
      // type check will catch missing cases
      const unknownVectorStoreType: never = config.store_type
      console.error(`Invalid vector store type: ${unknownVectorStoreType}`)
      return "unknown"
    }
  }
}

export function build_vector_store_options(
  vector_store_configs: VectorStoreConfig[],
) {
  return [
    {
      options: [
        {
          label: "New Search Index Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },
    ...(vector_store_configs.length > 0
      ? [
          {
            label: "Search Index Configurations",
            options: vector_store_configs.map((config) => ({
              label: fmt_vector_store_label(config),
              value: config.id,
              description:
                config.name +
                ` • ${config.properties.similarity_top_k ?? 10} results`,
            })),
          },
        ]
      : []),
  ] as OptionGroup[]
}

function fmt_reranker_label(config: RerankerConfig) {
  return `${get_model_friendly_name(config.model_name)} (${provider_name_from_id(config.model_provider_name)}) • ${config.top_n} results`
}

export function build_reranker_options(reranker_configs: RerankerConfig[]) {
  return [
    {
      options: [
        {
          label: "New Reranker Configuration",
          value: "create_new",
          badge: "New",
          badge_color: "primary",
        },
      ],
    },
    ...(reranker_configs.length > 0
      ? [
          {
            label: "Rerankers",
            options: reranker_configs.map((config) => ({
              label: fmt_reranker_label(config),
              value: config.id,
              description:
                config.name +
                (config.description ? " • " + config.description : ""),
            })),
          },
        ]
      : []),
  ] as OptionGroup[]
}
