# Create Spec With Copilot

**POST /api/projects/{project_id}/tasks/{task_id}/spec_with_copilot**

**Tags:** Copilot

Create a spec using Kiln Copilot.

This endpoint uses Kiln Copilot to create:
1. An Eval for the spec with the appropriate template
2. A judge EvalConfig (LLM-as-judge)
3. The Spec itself
Plus, per synthesis path:
- Eval builder (`single_turn` / `multi_turn`): the reviewed runs are
  tagged golden and carry the human's ratings and claim reviews; every
  other case becomes an EvalInput, dealt into the splits the request
  names. Nothing is generated at save time.
- Legacy v1 flow (`sdg_session_config`): generate examples via the
  copilot API and save them as TaskRuns, with the request's reviewed
  examples as golden.

A test split is EvalInput items, answered fresh at eval time.

If you don't need copilot, use POST /specs instead.

All models are validated before any saves occur. If validation fails,
no data is persisted.

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
|name|string|Yes|1-32 chars|
|definition|string|Yes|The spec definition string, built by client using buildSpecDefinition()|
|properties|one of: DesiredBehaviourProperties, IssueProperties, ToneProperties, FormattingProperties, LocalizationProperties, AppropriateToolUseProperties, ReferenceAnswerAccuracyProperties, FactualCorrectnessProperties, HallucinationsProperties, CompletenessProperties, ToxicityProperties, BiasProperties, MaliciousnessProperties, NsfwProperties, TabooProperties, JailbreakProperties, PromptLeakageProperties|Yes|The spec properties object, pre-built by client with spec_type included|
|evaluate_full_trace|boolean|No||
|reviewed_examples|array of ReviewedExample|No||
|judge_info.prompt|string|Yes||
|judge_info.model_name|string|Yes||
|judge_info.model_provider|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|splits|one of: array of SplitShare or null|No|The splits the eval is created with, each with its relative share of the unreviewed cases; list order wins a leftover case. Must name test. Required on a single_turn or multi_turn save.|
|sdg_session_config|one of: SyntheticDataGenerationSessionConfigApi or null|No||
|multi_turn|one of: MultiTurnSaveInfo or null|No||
|single_turn|one of: SingleTurnSaveInfo or null|No||
|task_prompt_with_example|one of: string or null|No||
|task_sample|one of: TaskSample or null|No||
|run_config_id|one of: string or null|No|Legacy `sdg_session_config` path only: the run config whose tools and skills describe the target task while examples are generated. Omit to use the task's default run config. The eval builder generates nothing, so this does not apply to it.|
|provenance|one of: KilnArtifactProvenance or null|No|Provenance stamped onto the created judge eval config. The judge belongs to a new eval, so derived_from_ids must be empty.|

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

### GradedClaim

One claim with a human grade on it.

A claim is one decision the judge made, written so the reviewer can vote
on it from the card alone. Grades have one direction on every claim:
agree means the judge got that decision right, disagree means it got it
wrong. The claim text carries its own evidence and citation markers.

|Field|Type|Required|Description|
|-|-|-|-|
|text|string|Yes|The claim as shown to the reviewer.|
|human_grade|string|Yes|The human's grade on this claim. One of: agree, disagree|
|human_feedback|one of: string or null|No|Optional plaintext reason for the grade.|

### ClaimReviewApi

The reviewer's grades on one trace's claim summary.

Mirrors the persisted ClaimReview shape (judge verdict, the overview,
every claim with its agree/disagree and optional why, and the reviewer's
overall call) so the save path can write it onto the golden TaskRun and
judge refinement can consume it later.

|Field|Type|Required|Description|
|-|-|-|-|
|judge_score|string|Yes|One of: pass, fail|
|judge_reasoning|string|Yes||
|overview|string|Yes||
|claims|array of GradedClaim|Yes||
|human_verdict|string|Yes|One of: pass, fail|

### ReviewedExample

A reviewed example from the spec review process.

Extends SampleApi with review-specific fields for tracking
model and user judgments on spec compliance.

|Field|Type|Required|Description|
|-|-|-|-|
|input|string|Yes||
|output|string|Yes||
|model_says_meets_spec|boolean|Yes||
|user_says_meets_spec|boolean|Yes||
|feedback|string|Yes||
|claim_review|one of: ClaimReviewApi or null|No|Per-claim grades from the claim review, when the example was reviewed that way (v2 builder).|

### SplitShare

One split of a new eval and its relative share of the dealt cases.

|Field|Type|Required|Description|
|-|-|-|-|
|split|string|Yes|One of: train, val, test|
|weight|integer|Yes|Relative share. No sum rule; 20/20/20 and 1/1/1 are the same deal. >=1.0|

### SyntheticDataGenerationSessionConfigApi

Configuration for a synthetic data generation session

|Field|Type|Required|Description|
|-|-|-|-|
|topic_generation_config.task_metadata.model_name|string|Yes|The name of the AI model used.|
|topic_generation_config.task_metadata.model_provider_name|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|topic_generation_config.prompt|string|Yes||
|input_generation_config.task_metadata.model_name|string|Yes|The name of the AI model used.|
|input_generation_config.task_metadata.model_provider_name|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|input_generation_config.prompt|string|Yes||
|output_generation_config.task_metadata.model_name|string|Yes|The name of the AI model used.|
|output_generation_config.task_metadata.model_provider_name|string|Yes|Enumeration of supported AI model providers. One of: openai, groq, amazon_bedrock, ollama, openrouter, fireworks_ai, kiln_fine_tune, kiln_custom_registry, openai_compatible, anthropic, gemini_api, azure_openai, huggingface, vertex, together_ai, siliconflow_cn, cerebras, docker_model_runner, featherless_ai, cloudflare, typesafe|
|output_generation_config.prompt|string|Yes||

### ReviewedChainApi

A reviewer's verdict on one multi-turn chain, keyed by its leaf run.

The leaf TaskRun id is the durable identity that rides from the drive
batch through review to save — the save path writes the golden rating
(and the claim review) onto that leaf.

|Field|Type|Required|Description|
|-|-|-|-|
|leaf_run_id|string|Yes||
|user_says_meets_spec|boolean|Yes||
|feedback|string|No||
|claim_review|one of: ClaimReviewApi or null|No||

### DrivenSyntheticCaseApi

One driven synthetic-user case from the builder session.

The save path mints an EvalInput from each unreviewed case — the
re-drivable input the eval runner regenerates a conversation from, per
run config. A reviewed case is the golden answer key instead.

|Field|Type|Required|Description|
|-|-|-|-|
|seed_prompt|string|Yes|The opening user-side message of the conversation. >=1 chars|
|synthetic_user_info|string|Yes|The XML-tagged persona blob as generated (persona/goal/behavior_guidance). Wire format only: the save path parses it into the structured submodel before anything persists. >=1 chars|
|scenario_index|one of: integer or null|No|Zero-based index into the builder's user-approved scenario plan identifying the scenario this case was generated from. Recorded on the minted EvalInput as a `scenario:{index}` provenance tag; omit when the case has no plan scenario.|
|leaf_run_id|string|Yes|The id of the chain-leaf TaskRun this case was driven in. A case whose run the human reviewed is represented by that rated run and is not minted. Empty when the drive recorded no run, which can never have been reviewed.|

### MultiTurnSaveInfo

An existing multi-turn synthetic-user batch to turn into an eval.

The reviewed chains become the golden answer key; every other case is minted
as an EvalInput the eval runner re-drives per run config.

|Field|Type|Required|Description|
|-|-|-|-|
|batch_tag|string|Yes|The batch_tag emitted by the multi-turn synthetic-user runner (see kiln_ai.synthetic_user.runner). Identifies the set of conversation chains already persisted to disk that this Eval should evaluate.|
|reviewed_chains|array of ReviewedChainApi|No|The human's review verdicts, one per reviewed chain keyed by leaf TaskRun id. Each becomes a golden RequirementRating on the chain leaf (plus Feedback / per-claim grades when present).|
|cases|array of DrivenSyntheticCaseApi|Yes|The driven synthetic-user cases of this batch. Each unreviewed one is minted as an EvalInput the runner re-drives per run config at eval time; a reviewed one is golden instead.|
|drive_config.model_name|string|Yes|The model that plays the synthetic user during re-drives.|
|drive_config.model_provider|string|Yes|The provider of the synthetic-user model.|
|drive_config.turns|integer|Yes|Ceiling on the assistant turns per re-driven conversation. 1.0-20.0|

### SingleTurnCaseApi

One case the single-turn pipeline ran: its input and the run it ran in.

|Field|Type|Required|Description|
|-|-|-|-|
|input|string|Yes|The generated task input the batch ran, as the pipeline ran it. On a task with an input schema this is the input encoded as a JSON string.|
|leaf_run_id|string|Yes|The id of the TaskRun this input was run in. A case whose run the human reviewed is represented by that rated run and is not minted. Empty when the pipeline recorded no run, which can never have been reviewed.|

### SingleTurnSaveInfo

An existing single-turn pipeline batch to turn into an eval.

The reviewed runs become the golden answer key; every other case is minted as
an EvalInput. Nothing is generated at save time.

|Field|Type|Required|Description|
|-|-|-|-|
|batch_tag|string|Yes|The batch_tag emitted by the single-turn pipeline (eval_builder single_turn_pipeline). Identifies the set of batch-tagged TaskRuns already persisted to disk that this Eval's golden runs are taken from.|
|reviewed_runs|array of ReviewedChainApi|No|The human's review verdicts, one per reviewed run keyed by TaskRun id (the run itself is the leaf on this arm). Each becomes a golden RequirementRating on the run (plus Feedback / per-claim grades when present).|
|inputs|array of SingleTurnCaseApi|Yes|The cases the batch actually ran. Each unreviewed one becomes an EvalInput the runner executes fresh per run config at eval time; a reviewed one is golden instead.|

### TaskSample

An example task input/output pair used to demonstrate expected behavior.

|Field|Type|Required|Description|
|-|-|-|-|
|input|string|Yes|The example input for the task.|
|output|string|Yes|The expected output for the task.|

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
