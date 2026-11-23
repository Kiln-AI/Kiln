# Create Spec

**POST /api/projects/{project_id}/tasks/{task_id}/specs**

**Tags:** Specs

Create a spec: a requirement for the task's output, with the eval that
measures it.

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
|name|string|Yes|The name of the spec. 1-32 chars|
|definition|string|Yes|A detailed definition of the spec. >=1 chars|
|properties|one of: DesiredBehaviourProperties, IssueProperties, ToneProperties, FormattingProperties, LocalizationProperties, AppropriateToolUseProperties, ReferenceAnswerAccuracyProperties, FactualCorrectnessProperties, HallucinationsProperties, CompletenessProperties, ToxicityProperties, BiasProperties, MaliciousnessProperties, NsfwProperties, TabooProperties, JailbreakProperties, PromptLeakageProperties|Yes|The properties of the spec.|
|priority|integer|No|Priority levels, where P0 is highest priority. One of: 0, 1, 2, 3|
|status|string|No|Lifecycle status of an eval (and, historically, of a spec). One of: active, future, deprecated, archived|
|tags|array of string|No|The tags of the spec.|
|evaluate_full_trace|boolean|No|Whether to evaluate the full trace instead of the final answer.|
|task_sample|one of: TaskSample or null|No|An example task input/output pair.|

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
|name|string|The name of the spec. 1-120 chars|
|definition|string|A detailed definition of the spec. >=1 chars|
|properties|one of: DesiredBehaviourProperties, IssueProperties, ToneProperties, FormattingProperties, LocalizationProperties, AppropriateToolUseProperties, ReferenceAnswerAccuracyProperties, FactualCorrectnessProperties, HallucinationsProperties, CompletenessProperties, ToxicityProperties, BiasProperties, MaliciousnessProperties, NsfwProperties, TabooProperties, JailbreakProperties, PromptLeakageProperties|The properties of the spec.|
|priority|integer|Priority levels, where P0 is highest priority. One of: 0, 1, 2, 3|
|status|string|Lifecycle status of an eval (and, historically, of a spec). One of: active, future, deprecated, archived|
|tags|array of string|The tags of the spec.|
|eval_id|one of: string or null|The id of the eval to use for this spec.|
|task_sample|one of: TaskSample or null|An example task input/output pair used to demonstrate expected behavior for this spec.|
|synthetic_data_generation_session_config|one of: SyntheticDataGenerationSessionConfig or null|Config for synthetic data generation session.|
|model_type|string||

### 422 Validation Error

Validation Error

|Field|Type|Description|
|-|-|-|
|detail|array of ValidationError||

## Schemas

### DesiredBehaviourProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: desired_behaviour|
|desired_behaviour_description|string|Yes||
|correct_behaviour_examples|string|No||
|incorrect_behaviour_examples|string|No||

### IssueProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: issue|
|issue_description|string|Yes||
|issue_examples|string|No||
|non_issue_examples|string|No||

### ToneProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: tone|
|core_requirement|string|Yes||
|tone_description|string|Yes||
|acceptable_examples|string|No||
|unacceptable_examples|string|No||

### FormattingProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: formatting|
|core_requirement|string|Yes||
|formatting_requirements|string|Yes||
|proper_formatting_examples|string|No||
|improper_formatting_examples|string|No||

### LocalizationProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: localization|
|core_requirement|string|Yes||
|localization_requirements|string|Yes||
|violation_examples|string|Yes||

### AppropriateToolUseProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: appropriate_tool_use|
|core_requirement|string|Yes||
|tool_use_guidelines|string|Yes||
|appropriate_tool_use_examples|string|Yes||
|inappropriate_tool_use_examples|string|Yes||
|tool_id|string|No||
|tool_function_name|string|No||

### ReferenceAnswerAccuracyProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: reference_answer_accuracy|
|core_requirement|string|Yes||
|reference_answer_accuracy_description|string|Yes||
|accurate_examples|string|Yes||
|inaccurate_examples|string|Yes||

### FactualCorrectnessProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: factual_correctness|
|core_requirement|string|Yes||
|factually_inaccurate_examples|string|Yes||

### HallucinationsProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: hallucinations|
|core_requirement|string|Yes||
|hallucinations_examples|string|Yes||

### CompletenessProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: completeness|
|core_requirement|string|Yes||
|complete_examples|string|Yes||
|incomplete_examples|string|Yes||

### ToxicityProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: toxicity|
|core_requirement|string|Yes||
|toxicity_examples|string|Yes||

### BiasProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: bias|
|core_requirement|string|Yes||
|bias_examples|string|Yes||

### MaliciousnessProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: maliciousness|
|core_requirement|string|Yes||
|malicious_examples|string|Yes||

### NsfwProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: nsfw|
|core_requirement|string|Yes||
|nsfw_examples|string|Yes||

### TabooProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: taboo|
|core_requirement|string|Yes||
|taboo_examples|string|Yes||

### JailbreakProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: jailbreak|
|core_requirement|string|Yes||
|jailbroken_examples|string|Yes||

### PromptLeakageProperties

|Field|Type|Required|Description|
|-|-|-|-|
|spec_type|string|Yes|One of: prompt_leakage|
|core_requirement|string|Yes||
|leakage_examples|string|Yes||

### TaskSample

An example task input/output pair used to demonstrate expected behavior.

|Field|Type|Required|Description|
|-|-|-|-|
|input|string|Yes|The example input for the task.|
|output|string|Yes|The expected output for the task.|

### SyntheticDataGenerationSessionConfig

Configuration for a synthetic data generation session.

|Field|Type|Required|Description|
|-|-|-|-|
|topic_generation_config.model_name|string|Yes|The model used for generation.|
|topic_generation_config.provider_name|string|Yes|The provider of the model used for generation.|
|topic_generation_config.prompt|string|Yes|The prompt used for generation.|
|input_generation_config.model_name|string|Yes|The model used for generation.|
|input_generation_config.provider_name|string|Yes|The provider of the model used for generation.|
|input_generation_config.prompt|string|Yes|The prompt used for generation.|
|output_generation_config.model_name|string|Yes|The model used for generation.|
|output_generation_config.provider_name|string|Yes|The provider of the model used for generation.|
|output_generation_config.prompt|string|Yes|The prompt used for generation.|

### ValidationError

|Field|Type|Required|Description|
|-|-|-|-|
|loc|array of one of: string, integer|Yes||
|msg|string|Yes||
|type|string|Yes||
|input|any|No||
|ctx|object|No||
