# Model Support


---

# This guide as moved to [our docs](https://docs.kiln.tech/docs/models-and-ai-providers). This page may be out of date.

We suggest reading the [latest version](https://docs.kiln.tech/docs/models-and-ai-providers).

---

## Original Content

Kiln can use essentially any LLM model.

Models come in a range of flavours, from very easy to use, to advanced methods for expert users

- [Included models](#included-models-recommended)
- [Custom Ollama models](#custom-ollama-models)
- [Custom models from existing providers](#custom-models-from-existing-providers)
- [Custom OpenAI compatible servers](#custom-openai-compatible-servers)
  - [LiteLLM](#litellm) - Anthropic, Huggingface, VertexAI, TogetherAI, and more.

## Included models [Recommended]

These models that have been tested to work with Kiln's various features (structured output, data gen, fine tuning, etc.). These are the easiest to use, and generally won't result in errors.

To get access to these models, simply connect any AI provider (in the Settings page). We suggest OpenRouter as it has the widest selection of models. Once connected, you can select the model you want to use in the model dropdown.

Note: some models may only work with unstructured output, or may not support data generation. The dropdown will warn if you try to use a model that doesn't support a feature.

Included models include common models like Claude, GPT-4, Llama, and many more. The complete list is available in the [Kiln Models](https://github.com/Kiln-AI/Kiln/blob/main/libs/core/kiln_ai/adapters/ml_model_list.py) guide.

## Custom Ollama Models

Any Ollama model you have installed on your server will be available to use in Kiln. To add models, simply install them with the Ollama CLI `ollama pull <model_name>`.

Some Ollama models are included/tested, and will automtically appear in the model dropdown. Any untested Ollama models will still appear in the dropdown, but in the "Untested" section.

## Custom Models from Existing Providers

If you want to use a model that is not in the list but is supported by one of our AI providers, you can use a custom model.

To use a custom model, click "Add Model" in the "AI Providers & Models" section of Settings.

These will appear in the "untested" section of the model dropdown.

## Custom OpenAI Compatible Servers

If you have an OpenAI compatible server (LiteLLM, vLLM, etc.), you can use it in Kiln.

To do this, add a "Custom API" in the "AI Providers & Models" section of Settings.

All models supported by this API will appear in the "untested" section of the model dropdown. 

Notes:
- The API must support the `/v1/models` endpoint, so Kiln can access the list of models.
- Many Kiln tasks require structured (JSON) output. These can be hard to get working on custom servers, as each server/model pair usually needs some configuration to reliably produce structured output (tools vs json_mode vs json parsing, schema format, etc).

### LiteLLM

Kiln works with [LiteLLM](https://github.com/BerriAI/litellm), an open source proxy which exposes an OpenAI compatible API to over 100 model providers. If your preferred provider isn't built in, try LiteLLM! Simply add your LiteLLM URL in the "Custom API" section of Settings. 
