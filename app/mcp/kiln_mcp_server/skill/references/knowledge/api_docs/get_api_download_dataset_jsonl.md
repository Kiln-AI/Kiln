# Download Dataset JSONL

**GET /api/download_dataset_jsonl**

**Tags:** Fine-tuning

Download one split of a dataset split as a JSONL file, in a fine-tuning
format.

## Request

### Query Parameters

|Name|Type|Required|Default|Description|
|-|-|-|-|-|
|project_id|string|Yes||The unique identifier of the project.|
|task_id|string|Yes||The unique identifier of the task within the project.|
|dataset_id|string|Yes||The unique identifier of the dataset split.|
|split_name|string|Yes||The name of the split to download (e.g., 'train', 'test', 'validation').|
|format_type|string|Yes||The format type for the JSONL output.|
|data_strategy|string|Yes||The data strategy for formatting the output.|
|system_message_generator|one of: string or null|No||The system message generator to use.|
|custom_system_message|one of: string or null|No||Custom system message if not using a generator.|
|custom_thinking_instructions|one of: string or null|No||Custom thinking instructions for thinking models.|

## Responses

### 200 OK

Successful Response

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
