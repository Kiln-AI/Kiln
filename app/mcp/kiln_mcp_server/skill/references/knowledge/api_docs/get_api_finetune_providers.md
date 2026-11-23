# List Finetune Providers

**GET /api/finetune_providers**

**Tags:** Fine-tuning

List the providers that can fine-tune, with the base models each offers and
whether it is enabled.

## Responses

### 200 OK

Successful Response

**Body:** array of FinetuneProvider

## Schemas

### FinetuneProviderModel

A model available for fine-tuning from a provider.

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|The display name of the model.|
|id|string|Yes|The provider's model identifier.|
|data_strategies_supported|array of string|No|The data strategies supported by this model.|
|supports_function_calling|boolean|No|Whether the model supports function calling.|

### FinetuneProvider

A provider that offers fine-tuning.

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|The display name of the provider.|
|id|string|Yes|The unique provider identifier used in API calls.|
|enabled|boolean|Yes|Whether this provider is enabled.|
|models|array of FinetuneProviderModel|Yes|The models available for fine-tuning.|
