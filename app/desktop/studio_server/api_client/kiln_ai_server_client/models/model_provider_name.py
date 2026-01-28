from enum import Enum


class ModelProviderName(str, Enum):
    AMAZON_BEDROCK = "amazon_bedrock"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    CEREBRAS = "cerebras"
    DOCKER_MODEL_RUNNER = "docker_model_runner"
    FIREWORKS_AI = "fireworks_ai"
    GEMINI_API = "gemini_api"
    GROQ = "groq"
    HUGGINGFACE = "huggingface"
    KILN_CUSTOM_REGISTRY = "kiln_custom_registry"
    KILN_FINE_TUNE = "kiln_fine_tune"
    OLLAMA = "ollama"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENROUTER = "openrouter"
    SILICONFLOW_CN = "siliconflow_cn"
    TOGETHER_AI = "together_ai"
    VERTEX = "vertex"

    def __str__(self) -> str:
        return str(self.value)
