# List Dataset Splits

**GET /api/projects/{project_id}/tasks/{task_id}/dataset_splits**

**Tags:** Fine-tuning

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

## Responses

### 200 OK

Successful Response

**Body:** array of DatasetSplit

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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
