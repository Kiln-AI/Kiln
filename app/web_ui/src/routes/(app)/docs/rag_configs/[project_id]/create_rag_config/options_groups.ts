import {
  embedding_model_name,
  get_model_friendly_name,
  provider_name_from_id,
} from "$lib/stores"
import type {
  ChunkerConfig,
  EmbeddingConfig,
  ExtractorConfig,
  VectorStoreConfig,
} from "$lib/types"
import type { OptionGroup } from "$lib/ui/fancy_select_types"
import {
  chunker_type_format,
  extractor_output_format,
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

function fmt_chunker_label(config: ChunkerConfig) {
  const props = config.properties
  switch (config.chunker_type) {
    case "fixed_window":
      return `${chunker_type_format(config.chunker_type)} • Size: ${props.chunk_size || "N/A"} words • Overlap: ${props.chunk_overlap || "N/A"} words`
    case "semantic":
      return `${chunker_type_format(config.chunker_type)} • Buffer: ${props.buffer_size || "N/A"} • Threshold: ${props.breakpoint_percentile_threshold || "N/A"}`
    default: {
      // type check will catch missing cases
      const unknownChunkerType: never = config.chunker_type
      console.error(`Invalid chunker type: ${unknownChunkerType}`)
      return "unknown"
    }
  }
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
                label: fmt_chunker_label(config),
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
