# Create Dataset Split

**POST /api/projects/{project_id}/tasks/{task_id}/dataset_splits**

**Tags:** Fine-tuning

Freeze a set of the task's runs into a dataset split for fine-tuning.

## Request

### Path Parameters

|Name|Type|Required|Description|
|-|-|-|-|
|project_id|string|Yes|The unique identifier of the project.|
|task_id|string|Yes|The unique identifier of the task within the project.|

### Request Body

**Content Type:** `application/json`

|Field|Type|Required|Description|
|-|-|-|-|
|dataset_split_type|string|Yes|Dataset split types used in the API. Any split type can be created in code. One of: train_val, train_test, train_test_val, train_test_val_80, all|
|filter_id|string|Yes|The dataset filter to use.|
|name|one of: string or null|No|The name of the dataset split.|
|description|one of: string or null|No|The description of the dataset split.|

## Responses

### 200 OK

Successful Response

|Field|Type|Description|
|-|-|-|
|v|integer|Schema version for migration support.|
|id|one of: string or null|Unique identifier for this record.|
|path|one of: string or null|File system path where the record is stored.|
|created_at|string|Timestamp when the model was created. Timezone-aware; stores the writer's local offset. Format: date-time|
|created_by|string|User ID of the creator.|
|name|string|The name of the dataset split. 1-120 chars|
|description|one of: string or null|A description of the dataset for you and your team. Not used in training.|
|splits|array of DatasetSplitDefinition|The splits in the dataset.|
|split_contents|object|The contents of each split in the dataset. The key is the split name, and the value is a list of task run IDs.|
|filter|one of: string or null|The filter used to build the dataset.|
|model_type|string||

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

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
