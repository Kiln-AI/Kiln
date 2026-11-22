# Get Finetune Dataset Info

**GET /api/projects/{project_id}/tasks/{task_id}/finetune_dataset_info**

**Tags:** Fine-tuning

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|tool_ids|one of: array of string or null|No||Optional list of tool/skill IDs to filter by.|
|empty_tool_filter|boolean|No|False|If true and tool_ids is None, treats as empty tool filter.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|existing_datasets|array of DatasetSplit|Existing dataset splits.|
|existing_finetunes|array of Finetune|Existing finetunes.|
|finetune_tags|array of FinetuneDatasetTagInfo|Tag statistics for finetune data.|
|eligible_datasets|array of DatasetSplit|Eligible dataset splits based on tool selection.|
|eligible_finetune_tags|array of FinetuneDatasetTagInfo|Eligible tag statistics based on tool selection.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### DatasetSplitDefinition

A definition of a split in a dataset.

Example: name="train", description="The training set", percentage=0.8 (80% of the dataset)

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|The name of the dataset split definition. 1-120 chars|
|description|one of: string or null|No|A description of the dataset for you and your team. Not used in training.|
|percentage|number|Yes|The percentage of the dataset that this split represents (between 0 and 1). 0.0-1.0|

### DatasetSplit

A collection of task runs, with optional splits (train, test, validation).

Used to freeze a dataset into train/test/validation splits for repeatable fine-tuning or other tasks.

Maintains a list of IDs for each split, to avoid data duplication.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|The name of the dataset split. 1-120 chars|
|description|one of: string or null|No|A description of the dataset for you and your team. Not used in training.|
|splits|array of DatasetSplitDefinition|No|The splits in the dataset.|
|split_contents|object|Yes|The contents of each split in the dataset. The key is the split name, and the value is a list of task run IDs.|
|filter|one of: string or null|No|The filter used to build the dataset.|
|model_type|string|Yes||

### ToolsRunConfig

A config describing which tools are available to a task.

|Field|Type|Required|Description|
|-|-|-|-|
|tools|array of string|Yes|The IDs of the tools available to the task.|

### JinjaInputTransform

Render the task input via a Jinja2 template, producing the first user
message sent to the model. See specs/projects/templates/functional_spec.md
for the full contract.

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: jinja|
|template|string|Yes|Jinja2 template source. Validated at save time.|

### KilnAgentRunConfigProperties

A configuration for running a task using a Kiln AI agent.

This includes everything needed to run a task, except the input and task ID. Running the same RunConfig with the same input should make identical calls to the model (output may vary as models are non-deterministic).

|Field|Type|Required|Description|
|-|-|-|-|
|type|string|No|One of: kiln_agent|
|model_name|string|Yes|The model to use for this run config.|
|model_provider_name|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|prompt_id|string|Yes|The prompt to use for this run config. Defaults to building a simple prompt from the task if not provided.|
|top_p|number|No|The top-p value to use for this run config. Defaults to 1.0.|
|temperature|number|No|The temperature to use for this run config. Defaults to 1.0.|
|structured_output_mode|string|Yes|Enumeration of supported structured output modes.

- json_schema: request json using API capabilities for json_schema
- function_calling: request json using API capabilities for function calling
- json_mode: request json using API's JSON mode, which should return valid JSON, but isn't checking/passing the schema
- json_instructions: append instructions to the prompt to request json matching the schema. No API capabilities are used. You should have a custom parser on these models as they will be returning strings.
- json_instruction_and_object: append instructions to the prompt to request json matching the schema. Also request the response as json_mode via API capabilities (returning dictionaries).
- json_custom_instructions: The model should output JSON, but custom instructions are already included in the system prompt. Don't append additional JSON instructions.
- default: let the adapter decide (legacy, do not use for new use cases)
- unknown: used for cases where the structured output mode is not known (on old models where it wasn't saved). Should lookup best option at runtime. One of: default, json_schema, function_calling_weak, function_calling, json_mode, json_instructions, json_instruction_and_object, json_custom_instructions, unknown|
|thinking_level|one of: string or null|No|The thinking level to use for this run config. If None, defaults may apply.|
|tools_config|one of: ToolsRunConfig or null|No|The tools config to use for this run config, defining which tools are available to the model.|
|input_transform|one of: JinjaInputTransform or null|No|Optional transform applied to the task input at run time, producing the first user message sent to the model. Default None preserves the identity path.|

### KilnArtifactProvenance

Why this artifact exists and what it was derived from.

Written once at creation; immutable thereafter (enforced at the API layer).
Compile-time metadata for future agent sessions and humans — never shown to
runtime models (not part of any tool/prompt surface).

|Field|Type|Required|Description|
|-|-|-|-|
|notes|one of: string or null|No|Why this artifact exists: the problem/hypothesis it addresses, what changed vs. the derived_from_ids parents, what validation/evidence supports it (cite eval/run_config/trace IDs inline), and known limits. First line = one-sentence summary. Record observations with conditions, never universal rules. Max ~2000 chars.|
|derived_from_ids|array of one of: string or null|No|IDs of same-type sibling artifacts this one was derived from. Ordered: first = primary parent (the artifact this replaces or is a new version of); further entries = additional sources merged in. Empty = not derived. IDs resolve among siblings in the same parent scope only.|
|origin|one of: string or null|No|Whose judgment created this artifact. 'human': a person authored it directly OR an agent created it fulfilling a direct human request. 'agent': an agent created it autonomously. None: unknown/legacy. Required when this provenance is created; consumers must tolerate unknown values.|

### Finetune

The Kiln fine-tune datamodel.

Initially holds a reference to a training job, with needed identifiers to update the status. When complete, contains the new model ID.

|Field|Type|Required|Description|
|-|-|-|-|
|v|integer|No|Schema version for migration support.|
|id|one of: string or null|No|Unique identifier for this record.|
|path|one of: string or null|No|File system path where the record is stored.|
|created_at|string|No|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|No|User ID of the creator.|
|name|string|Yes|The name of the fine-tune. 1-120 chars|
|description|one of: string or null|No|A description of the fine-tune for you and your team. Not used in training.|
|structured_output_mode|one of: string or null|No|Legacy field -- replaced by run_config.structured_output_mode. The mode to use to train the model for structured output, if it was trained with structured output. We should call the tuned model with this mode if set.|
|provider|string|Yes|The provider to use for the fine-tune (e.g. 'openai').|
|base_model_id|string|Yes|The id of the base model to use for the fine-tune. This string relates to the provider's IDs for their own models, not Kiln IDs.|
|provider_id|one of: string or null|No|The ID of the fine-tune job on the provider's side. May not be the same as the fine_tune_model_id.|
|fine_tune_model_id|one of: string or null|No|The ID of the fine-tuned model on the provider's side. May not be the same as the provider_id.|
|dataset_split_id|string|Yes|The ID of the dataset split to use for this fine-tune.|
|train_split_name|string|No|The name of the training split to use for this fine-tune.|
|validation_split_name|one of: string or null|No|The name of the validation split to use for this fine-tune. Optional.|
|parameters|object|No|The parameters to use for this fine-tune. These are provider-specific.|
|system_message|string|Yes|The system message to use for this fine-tune.|
|thinking_instructions|one of: string or null|No|The thinking instructions to use for this fine-tune. Only used when data_strategy is final_and_intermediate.|
|latest_status|string|No|The status type of a fine-tune job. One of: unknown, pending, running, completed, failed|
|properties|object|No|Properties of the fine-tune. Different providers may use different properties.|
|data_strategy|string|No|Strategy for how a chat is structured. One of: final_only, final_and_intermediate, two_message_cot, final_and_intermediate_r1_compatible|
|run_config|one of: KilnAgentRunConfigProperties or null|No|The run configuration for this fine-tune.|
|provenance|one of: KilnArtifactProvenance or null|No|Why this artifact exists and what it was derived from.|
|model_type|string|Yes||

### FinetuneDatasetTagInfo

Statistics about task runs with a specific tag.

|Field|Type|Required|Description|
|-|-|-|-|
|tag|string|Yes|The tag applied to matching runs.|
|count|integer|Yes|Total number of runs with this tag.|
|reasoning_count|integer|Yes|Number of runs with reasoning data.|
|high_quality_count|integer|Yes|Number of high-quality runs.|
|reasoning_and_high_quality_count|integer|Yes|Number of high-quality runs with reasoning data.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
