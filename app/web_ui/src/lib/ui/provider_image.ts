import type { ModelProviderName } from "$lib/types"

const provider_image_map: Record<ModelProviderName | "wandb", string> = {
  openai: "/images/openai.svg",
  openrouter: "/images/openrouter.svg",
  anthropic: "/images/anthropic.svg",
  groq: "/images/groq.svg",
  ollama: "/images/ollama.svg",
  docker_model_runner: "/images/docker.svg",
  gemini_api: "/images/gemini.svg",
  vertex: "/images/google_logo.svg",
  amazon_bedrock: "/images/aws.svg",
  fireworks_ai: "/images/fireworks.svg",
  azure_openai: "/images/azure_openai.svg",
  huggingface: "/images/hugging_face.svg",
  together_ai: "/images/together_ai.svg",
  openai_compatible: "/images/api.svg",
  kiln_fine_tune: "/images/logo.svg",
  kiln_custom_registry: "/images/logo.svg",
  wandb: "/images/wandb.svg",
  siliconflow_cn: "/images/siliconflow.svg",
  cerebras: "/images/cerebras.svg",
  mistral: "/images/mistral.svg",
}

export function get_provider_image(provider_name: string) {
  if (provider_name in provider_image_map) {
    return provider_image_map[provider_name as ModelProviderName]
  }
  return "/images/api.svg"
}
