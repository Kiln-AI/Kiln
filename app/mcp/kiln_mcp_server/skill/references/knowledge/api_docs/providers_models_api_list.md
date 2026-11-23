# Providers & Models API

List and manage AI providers and models.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/providers/models`|GET|List Provider Models|List every model in Kiln's built-in model list, by ID and name.|get_api_providers_models.md|
|`/api/available_models`|GET|List Available Models|List the models the user can run now, grouped by connected provider, with each model's capabilities.|get_api_available_models.md|
|`/api/providers/embedding_models`|GET|List Provider Embedding Models|List every embedding model in Kiln's built-in list, by ID and name.|get_api_providers_embedding_models.md|
|`/api/available_embedding_models`|GET|List Available Embedding Models|List the embedding models the user can run now, grouped by connected provider.|get_api_available_embedding_models.md|
|`/api/providers/reranker_models`|GET|List Provider Reranker Models|List every reranker model in Kiln's built-in list, by ID and name.|get_api_providers_reranker_models.md|
|`/api/available_reranker_models`|GET|List Available Reranker Models|List the reranker models the user can run now, grouped by connected provider.|get_api_available_reranker_models.md|
|`/api/provider/ollama/connect`|POST|Connect Ollama|Connect to a running Ollama server and list its models. Uses the default address unless custom_ollam...|post_api_provider_ollama_connect.md|
|`/api/provider/docker_model_runner/connect`|POST|Connect Docker Model Runner|Connect to a running Docker Model Runner and list its models. Uses the default address unless a cust...|post_api_provider_docker_model_runner_connect.md|
|`/api/settings/available_providers`|GET|List Available Providers|Returns all providers that can have custom models added.|get_api_settings_available_providers.md|
|`/api/settings/user_models`|GET|List User Models|Returns all user-defined models (new registry + legacy combined).  Includes both user_model_registry...|get_api_settings_user_models.md|
|`/api/settings/user_models`|POST|Add User Model|Add a user-defined model to the registry.|post_api_settings_user_models.md|
|`/api/settings/user_models`|DELETE|Delete User Model|Delete a user-defined model from the registry.  Supports two deletion methods: 1. By ID (new): Pass ...|delete_api_settings_user_models.md|
|`/api/provider/verify_kiln_copilot_api_key`|GET|Verify Kiln Copilot API Key|Verify the stored Kiln Copilot API key against the Kiln server.  Returns `{is_valid: bool}`. A stale...|get_api_provider_verify_kiln_copilot_api_key.md|
|`/api/model_info/models`|GET|List Model Info|List Kiln's models, with prices and limits, and whether each can run now.  Prices, limits and releas...|get_api_model_info_models.md|
|`/api/model_info/model_details`|GET|Get Model Info Details|Get the full record of one model by its Kiln model ID, for every provider.  Every provider entry has...|get_api_model_info_model_details.md|
|`/api/model_info/providers`|GET|List Model Info Providers|List the model providers Kiln knows, and whether each one is connected.  Each is marked connected or...|get_api_model_info_providers.md|
