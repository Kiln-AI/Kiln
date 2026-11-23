# List Prompts

**GET /api/projects/{project_id}/tasks/{task_id}/prompts**

**Tags:** Prompts

List the task's prompts and prompt generators, with the ID to use for each.

Includes saved prompts and the prompts of fine-tunes and run configs.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|generators|array of PromptGenerator|The available prompt generators.|
|prompts|array of ApiPrompt|The saved prompts for the task.|

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### PromptGenerator

A built-in prompt generator that can construct prompts from a task.

|Field|Type|Required|Description|
|-|-|-|-|
|id|string|Yes|The unique identifier of the generator.|
|short_description|string|Yes|A brief description of the generator.|
|description|string|Yes|A detailed description of the generator.|
|name|string|Yes|The display name of the generator.|
|chain_of_thought|boolean|Yes|Whether the generator includes chain of thought instructions.|

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

### ApiPrompt

A prompt with its PromptId and metadata.

|Field|Type|Required|Description|
|-|-|-|-|
|name|string|Yes|The name of the prompt. 1-120 chars|
|description|one of: string or null|No|A more detailed description of the prompt.|
|generator_id|one of: string or null|No|The id of the generator that created this prompt.|
|prompt|string|Yes|The prompt for the task. >=1 chars|
|chain_of_thought_instructions|one of: string or null|No|Instructions for the model 'thinking' about the requirement prior to answering. Used for chain of thought style prompting. COT will not be used unless this is provided.|
|id|string|Yes|The prompt ID used to reference this prompt.|
|type|string|Yes|The type label for this prompt (e.g. 'Custom', 'Fine-Tune', 'Frozen', 'Few-Shot').|
|created_at|one of: string or null|No|When the prompt was created.|
|created_by|one of: string or null|No|The user who created the prompt.|
|provenance|one of: KilnArtifactProvenance or null|No|Why this prompt exists and what it was derived from, if recorded.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
