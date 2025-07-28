export type ProviderSettings = Record<string, unknown>

/**
 * Checks if a specific provider is connected based on settings
 */
export function checkProviderConnection(
  provider_id: string,
  settings: ProviderSettings,
): boolean {
  switch (provider_id) {
    case "openai":
      return !!settings["open_ai_api_key"]
    case "anthropic":
      return !!settings["anthropic_api_key"]
    case "groq":
      return !!settings["groq_api_key"]
    case "openrouter":
      return !!settings["open_router_api_key"]
    case "amazon_bedrock":
      return !!(
        settings["bedrock_access_key"] && settings["bedrock_secret_key"]
      )
    case "fireworks_ai":
      return !!(
        settings["fireworks_api_key"] && settings["fireworks_account_id"]
      )
    case "vertex":
      return !!(settings["vertex_project_id"] && settings["vertex_location"])
    case "gemini_api":
      return !!settings["gemini_api_key"]
    case "azure_openai":
      return !!(
        settings["azure_openai_api_key"] && settings["azure_openai_endpoint"]
      )
    case "huggingface":
      return !!settings["huggingface_api_key"]
    case "together_ai":
      return !!settings["together_api_key"]
    case "wandb":
      return !!settings["wandb_api_key"]
    case "openai_compatible":
      return !!(
        settings["openai_compatible_providers"] &&
        Array.isArray(settings["openai_compatible_providers"]) &&
        settings["openai_compatible_providers"].length > 0
      )
    case "ollama":
      // Ollama is handled separately as it's checked via connection rather than API key
      return !!settings["ollama_base_url"]
    default:
      return false
  }
}
