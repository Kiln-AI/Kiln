import type { ModelProviderName } from "$lib/types"
import { client } from "$lib/api_client"
import {
  default_extractor_document_prompts,
  default_extractor_image_prompts,
  default_extractor_video_prompts,
  default_extractor_audio_prompts,
} from "../../routes/(app)/docs/extractors/[project_id]/create_extractor/default_extractor_prompts"

export async function create_default_extractor_config(
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

export async function create_default_chunker_config(
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
