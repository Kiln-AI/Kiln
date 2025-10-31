import type { ChunkerConfig } from "$lib/types"

export const fixedWindowChunkerProperties = (config: ChunkerConfig) => {
  if (config.chunker_type !== "fixed_window") {
    throw new Error("Chunker type is not fixed window")
  }
  if (
    "chunk_size" in config.properties &&
    "chunk_overlap" in config.properties
  ) {
    return config.properties
  }
  throw new Error(
    "Chunk size and chunk overlap are required for fixed window chunker",
  )
}

export const semanticChunkerProperties = (config: ChunkerConfig) => {
  if (config.chunker_type !== "semantic") {
    throw new Error("Chunker type is not semantic")
  }
  if (
    "embedding_config_id" in config.properties &&
    "buffer_size" in config.properties &&
    "breakpoint_percentile_threshold" in config.properties
  ) {
    return config.properties
  }
  throw new Error(
    "Embedding config id, buffer size, and breakpoint percentile threshold are required for semantic chunker",
  )
}
