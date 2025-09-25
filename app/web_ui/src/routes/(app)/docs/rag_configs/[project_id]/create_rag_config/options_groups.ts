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
import { extractor_output_format } from "$lib/utils/formatters"

function fmt_extractor_label(extractor: ExtractorConfig) {
  return `${get_model_friendly_name(extractor.model_name)} (${provider_name_from_id(extractor.model_provider_name)}) - ${extractor_output_format(extractor.output_format)}`
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
  return [
    config.properties?.chunk_size !== null &&
    config.properties.chunk_size !== undefined
      ? `Size: ${config.properties.chunk_size} words`
      : null,
    config.properties?.chunk_overlap !== null &&
    config.properties.chunk_overlap !== undefined
      ? `Overlap: ${config.properties.chunk_overlap} words`
      : null,
  ]
    .filter(Boolean)
    .join(" - ")
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
            options: chunker_configs.map((config) => ({
              label: fmt_chunker_label(config),
              value: config.id,
              description:
                config.name +
                (config.description ? ` - ${config.description}` : ""),
            })),
          },
        ]
      : []),
  ] as OptionGroup[]
}

function fmt_embedding_label(config: EmbeddingConfig) {
  return (
    `${embedding_model_name(config.model_name, config.model_provider_name)} (${provider_name_from_id(config.model_provider_name)})` +
    (config.properties?.dimensions
      ? `- ${config.properties?.dimensions} dimensions`
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
                (config.description ? " - " + config.description : ""),
            })),
          },
        ]
      : []),
  ] as OptionGroup[]
}

function fmt_vector_store_label(config: VectorStoreConfig) {
  return config.store_type === "lancedb_fts"
    ? "Full Text Search"
    : config.store_type === "lancedb_vector"
      ? "Vector Search"
      : "Hybrid Search"
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
                ` (${config.properties.similarity_top_k ?? 10} results)`,
            })),
          },
        ]
      : []),
  ] as OptionGroup[]
}
