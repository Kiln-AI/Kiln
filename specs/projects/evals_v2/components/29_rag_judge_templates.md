---
status: complete
approved: true
alignment_refs: []
opens: []
summary: First-party RAG judge template library — 6 llm_judge templates against canonical reference-key contract.
---

# RAG Judge Templates -- Stage 5 Design

**Author:** sub-agent, 2026-05-22
**Inputs:** A1.2 (reference shape), A1.3 (per-config reference-key declaration), A2.4 (V2 type catalog) from reference/ALIGNMENT.md; competitive_deepeval.md, competitive_synthesis.md, competitive_braintrust.md, competitive_langsmith.md, competitive_arize.md, competitive_promptfoo.md

---

## 1. Goal and scope

Ship 6 first-party `llm_judge` templates that make Kiln credible for RAG evaluation in V2.0 with zero schema work. Each template is a production-quality judge prompt that scores one dimension of RAG pipeline quality, consuming a documented subset of reference keys from `EvalInput.reference: dict[str, JsonValue]` (per A1.2). This deliverable is independent of the `llm_judge` type design itself (`components/21_type_llm_judge.md`) -- it slots in as template content for an already-designed EvalConfigType. Not shipping: embedding-based similarity metrics, end-to-end retrieval execution, RAGAS-style composite scoring, or production trace ingestion. All four are deferred per PLAN.md Phase 7 or declared out of scope for V2 entirely.

---

## 2. Reference-key contract

Per A1.2, `EvalInput.reference` is `dict[str, JsonValue] | None`. Per A1.3, each EvalConfig declares which keys it consumes, and validation happens at config-bind time (not at EvalInput creation time). The six RAG templates in this library consume three canonical reference keys. Projects using these templates must populate the relevant keys on each EvalInput before running the eval.

### 2.1. `retrieved_context`

- **Type:** `list[str]`
- **Semantics:** The text chunks returned by the RAG retrieval system in response to the user query. Each string is one chunk (a paragraph, a document section, a search result snippet). Order should reflect retrieval rank where applicable.
- **When populated:** At EvalInput creation time, by the user's data pipeline or import process. Typically extracted from production RAG logs, a retrieval API response, or manually authored for test cases.
- **Validation rules:** Must be a non-empty list. Each element must be a non-empty string. The template prompts instruct the judge to handle cases where context is thin (single short chunk) but an empty list is an input error, not an edge case.
- **Consumed by:** Faithfulness, Context Relevance, Context Precision, Hallucination.
- **Example value:**
  ```json
  [
    "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France. It was constructed from 1887 to 1889.",
    "The tower is 330 metres tall and was the tallest man-made structure in the world until 1930.",
    "Gustave Eiffel's company designed and built the tower for the 1889 World's Fair."
  ]
  ```

### 2.2. `ground_truth_context`

- **Type:** `list[str]`
- **Semantics:** The ideal source passages that *should* have been retrieved for this query. These represent the authoritative, complete set of passages a perfect retriever would return. Used to evaluate retrieval quality by comparing against what the system actually retrieved.
- **When populated:** At EvalInput creation time. Typically authored by a domain expert, extracted from a curated knowledge base, or derived from annotated evaluation datasets. More labor-intensive to produce than `retrieved_context`.
- **Validation rules:** Must be a non-empty list. Each element must be a non-empty string.
- **Consumed by:** Context Precision (optional -- improves scoring when available). Context Recall is deferred to Phase 7 (requires embedding similarity).
- **Example value:**
  ```json
  [
    "The Eiffel Tower was built by Gustave Eiffel's engineering company for the 1889 Exposition Universelle (World's Fair) held in Paris.",
    "At 330 metres, the Eiffel Tower was the world's tallest structure from its completion in 1889 until the Chrysler Building in New York surpassed it in 1930."
  ]
  ```

### 2.3. `reference_answer`

- **Type:** `str`
- **Semantics:** The gold-standard answer to the user's query. This is the factually correct, complete answer a human expert would give. Used to evaluate whether the model's output is factually accurate and complete, independent of what context was retrieved.
- **When populated:** At EvalInput creation time. Authored by domain experts or derived from curated Q&A datasets. Not required for context-only or faithfulness-only evaluations.
- **Validation rules:** Must be a non-empty string.
- **Consumed by:** Answer Correctness.
- **Example value:**
  ```json
  "The Eiffel Tower is a wrought-iron lattice tower located on the Champ de Mars in Paris. It was designed by Gustave Eiffel's engineering company and built between 1887 and 1889 for the 1889 World's Fair. It stands 330 metres tall."
  ```

### 2.4. Reference-key summary table

| Key | Type | Required by templates | Optional for |
|-----|------|-----------------------|-------------|
| `retrieved_context` | `list[str]` | Faithfulness, Context Relevance, Context Precision, Hallucination | -- |
| `ground_truth_context` | `list[str]` | -- | Context Precision |
| `reference_answer` | `str` | Answer Correctness | -- |

Per A1.3, each template below documents which reference keys it consumes (via `required_var` Jinja2 expressions on the `LlmJudgeProperties`). At run time, the runner validates that the required keys are present in the EvalInput's `reference` dict; missing keys cause the case to be skipped with `SkippedReason.missing_reference_key` (presence check only, no type checking).

---

## 3. Templates

Each template is a complete `llm_judge` EvalConfig. The judge prompt uses Kiln's template variable syntax (per `components/40_template_and_extraction.md` section 2): `{{ final_message }}` for the model's response, `{{ task_input }}` for the original user input, and `{{ reference_data.retrieved_context }}`, `{{ reference_data.reference_answer }}`, `{{ reference_data.ground_truth_context }}` for the corresponding reference-key values. These four reserved top-level variables (`final_message`, `trace`, `reference_data`, `task_input`) are populated by the eval runner's `EvalTaskInput` assembly (see `components/40_template_and_extraction.md`).

All six templates use a reasoning-then-verdict structure. The judge is asked to reason step-by-step before producing a score. This aligns with the G-Eval-style chain-of-thought pattern noted in A2.2 -- though these templates do not use `g_eval` (token-log-prob scoring). They use standard structured-output scoring.

---

### 3.1. Faithfulness

**Purpose:** Measure the fraction of claims in the model's output that are supported by the retrieved context. This is the core hallucination-detection metric for RAG systems, answering: "Did the model stick to what the retriever gave it?"

**Consumes reference keys:** `retrieved_context`

**Score type:** 0-1 continuous (fraction of faithful claims)

**Judge prompt:**

```
You are an expert fact-checker evaluating whether a response is faithful to its source context. Your task is to determine what fraction of the claims in the response are supported by the provided context.

## Inputs

**User query:**
{{ task_input }}

**Retrieved context (the only information the system had access to):**
{% for chunk in reference_data.retrieved_context %}
[Chunk {{ loop.index }}]: {{ chunk }}
{% endfor %}

**Response to evaluate:**
{{ final_message }}

## Instructions

Follow these steps precisely:

### Step 1: Extract claims
Break the response into individual, atomic factual claims. Each claim should be a single assertion that can be independently verified. Ignore filler phrases, hedging language, and meta-commentary (e.g., "Based on the provided information..."). If the response contains no factual claims (e.g., it is a refusal or a clarifying question), note this.

### Step 2: Verify each claim
For each extracted claim, determine whether it is:
- **Supported**: The claim is directly stated in or logically entailed by the retrieved context.
- **Not supported**: The claim cannot be verified from the retrieved context. This includes claims that are plausible but not present in the context, as well as claims that contradict the context.

A claim is "supported" only if the retrieved context provides sufficient evidence. General knowledge or common sense does NOT count as support -- only the retrieved context matters.

### Step 3: Calculate the faithfulness score
Faithfulness = (number of supported claims) / (total number of claims).
If there are zero claims, the score is 1.0.

## Output format

Return your analysis as JSON with this exact structure:

{
  "claims": [
    {"claim": "<atomic claim text>", "supported": true, "evidence": "<quote or paraphrase from context, or null if not supported>"},
    ...
  ],
  "num_supported": <integer>,
  "num_total": <integer>,
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<1-2 sentence summary of the faithfulness assessment>"
}
```

**Expected output format:** JSON object with `claims` array (each with `claim`, `supported`, `evidence`), `num_supported`, `num_total`, `score` (float 0-1), and `reasoning`.

**Edge cases the prompt handles:**
- **Empty or refusal response:** Zero claims extracted; score defaults to 1.0 (no unfaithful claims).
- **Single-chunk context:** Works identically -- claims are verified against the one available chunk.
- **Response restates context verbatim:** All claims are supported; score is 1.0. This is correct behavior (faithfulness does not penalize lack of synthesis).
- **Mixed supported/unsupported claims:** Partial score reflects the proportion.
- **Common knowledge not in context:** Treated as not supported. This is by design -- faithfulness measures grounding in the provided context, not general accuracy.

**Validation strategy:**
- Hand-label 50-100 RAG response samples with per-claim faithfulness judgments. Compare template scores against human labels. Target: Spearman rho >= 0.7.
- Cross-validate against DeepEval's Faithfulness metric on a shared dataset (DeepEval uses claim extraction followed by NLI-style verification, a similar approach).
- Test on adversarial cases: responses that blend context facts with plausible fabrications.

---

### 3.2. Answer Relevance

**Purpose:** Evaluate whether the model's output actually addresses the user's query. Detects irrelevant, off-topic, or evasive responses regardless of whether they are factually grounded.

**Consumes reference keys:** (none -- this template uses only `{{ final_message }}` and `{{ task_input }}`)

**Score type:** 0-1 continuous

**Judge prompt:**

```
You are an expert evaluator assessing whether a response is relevant to the user's query. A relevant response directly addresses what the user asked, provides information the user was seeking, and stays on topic.

## Inputs

**User query:**
{{ task_input }}

**Response to evaluate:**
{{ final_message }}

## Instructions

Follow these steps precisely:

### Step 1: Identify the user's intent
Determine what the user is asking for. Identify the core question or request, including any specific constraints (e.g., time period, format, scope).

### Step 2: Assess relevance dimensions
Evaluate the response on three dimensions:

1. **Addresses the question:** Does the response provide an answer to what was actually asked? A response that discusses the right topic but answers a different question is not fully relevant.
2. **Completeness:** Does the response cover the key aspects of the query, or does it address only a tangential part?
3. **Conciseness:** Is the response free of substantial irrelevant content that dilutes the answer? Minor filler is acceptable; large irrelevant digressions are not.

### Step 3: Assign a score
- **1.0**: The response directly and completely addresses the query with no significant irrelevant content.
- **0.7-0.9**: The response addresses the query but is partially incomplete or contains some irrelevant content.
- **0.4-0.6**: The response is tangentially related to the query but misses the core question or includes substantial irrelevant material.
- **0.1-0.3**: The response is mostly irrelevant to the query, addressing a different topic or providing unusable information.
- **0.0**: The response is completely irrelevant, a non-sequitur, or a refusal to answer without justification.

Note: A well-justified refusal (e.g., "I don't have enough information to answer that") should score 0.3-0.5 depending on whether the refusal is appropriate given the context.

## Output format

Return your analysis as JSON with this exact structure:

{
  "user_intent": "<1-2 sentence summary of what the user is asking>",
  "addresses_question": "<assessment of whether the response answers what was asked>",
  "completeness": "<assessment of coverage>",
  "conciseness": "<assessment of irrelevant content>",
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<1-2 sentence summary>"
}
```

**Expected output format:** JSON object with `user_intent`, `addresses_question`, `completeness`, `conciseness`, `score` (float 0-1), and `reasoning`.

**Edge cases the prompt handles:**
- **Refusal responses:** Scored contextually (0.3-0.5) rather than as a binary failure. A justified refusal is better than an irrelevant answer.
- **Partial answers:** Intermediate scores (0.7-0.9) capture responses that are relevant but incomplete.
- **Verbose but correct responses:** Conciseness dimension penalizes dilution without penalizing thoroughness.
- **Ambiguous queries:** The judge infers intent from the query text; ambiguity is noted in the reasoning.

**Validation strategy:**
- Hand-label 50-100 query-response pairs on a 5-point relevance scale. Convert to 0-1 and compare against template scores. Target: Spearman rho >= 0.7.
- Include adversarial cases: responses that are fluent and confident but address a different question.

---

### 3.3. Context Relevance

**Purpose:** Evaluate whether the chunks in `retrieved_context` are relevant to the user's query. This measures retriever quality (query-context alignment), not generator quality. A low score indicates the retriever is returning noise.

**Consumes reference keys:** `retrieved_context`

**Score type:** 0-1 continuous (fraction of relevant chunks)

**Judge prompt:**

```
You are an expert evaluator assessing the relevance of retrieved context to a user's query. Your task is to determine what fraction of the retrieved chunks contain information that is useful for answering the query.

## Inputs

**User query:**
{{ task_input }}

**Retrieved context chunks:**
{% for chunk in reference_data.retrieved_context %}
[Chunk {{ loop.index }}]: {{ chunk }}
{% endfor %}

## Instructions

Follow these steps precisely:

### Step 1: Identify the information need
Determine what information would be needed to answer the user's query comprehensively. List the key topics, entities, or facts required.

### Step 2: Evaluate each chunk
For each retrieved chunk, determine whether it is:
- **Relevant**: The chunk contains information that would be useful for answering the query. It does not need to fully answer the query -- partial relevance counts. A chunk about a related sub-topic that provides necessary context is relevant.
- **Irrelevant**: The chunk does not contain information useful for answering the query. It may discuss unrelated topics, or the same broad domain but a different specific question.

Be generous with relevance -- if a chunk provides any useful background, definitions, or context that supports answering the query, it is relevant. Only mark chunks as irrelevant if they would not help a knowledgeable person construct an answer.

### Step 3: Calculate the context relevance score
Context Relevance = (number of relevant chunks) / (total number of chunks).

## Output format

Return your analysis as JSON with this exact structure:

{
  "information_need": "<summary of what information is needed to answer the query>",
  "chunk_evaluations": [
    {"chunk_index": 1, "relevant": true, "reason": "<why this chunk is or is not relevant>"},
    ...
  ],
  "num_relevant": <integer>,
  "num_total": <integer>,
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<1-2 sentence summary of retrieval quality>"
}
```

**Expected output format:** JSON object with `information_need`, `chunk_evaluations` array (each with `chunk_index`, `relevant`, `reason`), `num_relevant`, `num_total`, `score` (float 0-1), and `reasoning`.

**Edge cases the prompt handles:**
- **Single chunk retrieved:** Score is binary (0.0 or 1.0). The template handles this naturally.
- **All chunks irrelevant:** Score is 0.0. The reasoning field explains why the retriever failed.
- **Partially relevant chunks:** A chunk that provides useful background but does not directly answer the query is marked relevant. The prompt instructs a generous relevance threshold.
- **Very long chunks:** The judge evaluates relevance of the chunk as a whole, not sentence-by-sentence.
- **Duplicate chunks:** Each is evaluated independently. Duplicates are not penalized by this metric (that would be a retriever-efficiency metric, out of scope).

**Validation strategy:**
- Hand-label 50-100 query-context pairs at the chunk level (relevant/irrelevant per chunk). Compare template chunk-level judgments against human labels. Target: per-chunk agreement >= 80%.
- Compare aggregate scores against DeepEval's Contextual Relevancy metric on a shared dataset.

---

### 3.4. Context Precision

**Purpose:** Measure what fraction of `retrieved_context` chunks were actually useful for producing a correct answer. Evaluates retriever signal-to-noise: a high-precision retriever returns mostly useful chunks, while a low-precision retriever dilutes relevant chunks with noise. Optionally compares against `ground_truth_context` if available, which provides a stronger signal.

**Consumes reference keys:** `retrieved_context`, optionally `ground_truth_context`

**Score type:** 0-1 continuous (fraction of useful chunks)

**Judge prompt:**

```
You are an expert evaluator measuring the precision of a retrieval system. Your task is to determine what fraction of the retrieved context chunks were actually useful for producing a correct, complete answer to the user's query.

## Inputs

**User query:**
{{ task_input }}

**Retrieved context chunks:**
{% for chunk in reference_data.retrieved_context %}
[Chunk {{ loop.index }}]: {{ chunk }}
{% endfor %}

{% if reference_data.ground_truth_context %}
**Ground truth context (the ideal passages that should have been retrieved):**
{% for chunk in reference_data.ground_truth_context %}
[Ground Truth {{ loop.index }}]: {{ chunk }}
{% endfor %}
{% endif %}

## Instructions

Follow these steps precisely:

### Step 1: Understand the ideal answer
{% if reference_data.ground_truth_context %}
Use the ground truth context to understand what a complete, correct answer looks like. The ground truth passages represent the authoritative source material.
{% else %}
Based on the query, determine what information would be needed for a complete, correct answer. Use your best judgment about what constitutes a useful passage for this query.
{% endif %}

### Step 2: Evaluate each retrieved chunk for usefulness
For each retrieved chunk, determine whether it is:
{% if reference_data.ground_truth_context %}
- **Useful**: The chunk contains information that overlaps with or supports the ground truth context. It provides facts, evidence, or explanations that would help produce the correct answer as represented by the ground truth.
- **Not useful**: The chunk does not contain information relevant to the ground truth context. It may be topically related but does not contribute to producing the correct answer.
{% else %}
- **Useful**: The chunk contains information that directly contributes to answering the query correctly. It provides facts, evidence, or explanations needed for a good answer.
- **Not useful**: The chunk does not contribute meaningful information toward answering the query. It may be topically adjacent but does not help produce a correct answer.
{% endif %}

### Step 3: Calculate the precision score
Context Precision = (number of useful chunks) / (total number of retrieved chunks).

## Output format

Return your analysis as JSON with this exact structure:

{
  "mode": "{{ 'with_ground_truth' if reference_data.ground_truth_context else 'without_ground_truth' }}",
  "chunk_evaluations": [
    {"chunk_index": 1, "useful": true, "reason": "<why this chunk is or is not useful>"},
    ...
  ],
  "num_useful": <integer>,
  "num_total": <integer>,
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<1-2 sentence summary of retrieval precision>"
}
```

**Expected output format:** JSON object with `mode` (indicating whether ground truth was available), `chunk_evaluations` array (each with `chunk_index`, `useful`, `reason`), `num_useful`, `num_total`, `score` (float 0-1), and `reasoning`.

**Edge cases the prompt handles:**
- **No `ground_truth_context` provided:** The prompt degrades gracefully to a query-only usefulness assessment. The `mode` field in the output records which path was taken.
- **All retrieved chunks are useful:** Score is 1.0 -- the retriever has perfect precision (though not necessarily recall; that is a separate metric).
- **Single chunk retrieved:** Binary score.
- **Ground truth and retrieved context have partial overlap:** The judge evaluates each retrieved chunk independently against the full set of ground truth passages.

**Validation strategy:**
- Hand-label 50-100 query-context pairs with per-chunk usefulness labels. Compare template per-chunk judgments against human labels.
- When ground truth is available, compare against DeepEval's Contextual Precision metric. Target: Spearman rho >= 0.7 on aggregate scores.

---

### 3.5. Hallucination

**Purpose:** Detect whether the model's output contains claims that contradict or fabricate content not present in the retrieved context. This is the inverse framing of Faithfulness -- both detect the same failure mode, but Hallucination is framed as a defect-detection metric (higher score = more hallucination = worse). Shipping both templates is intentional: users migrating from DeepEval or LangSmith expect a "Hallucination" metric by name, and the inverted framing is more intuitive for defect-tracking dashboards.

**Consumes reference keys:** `retrieved_context`

**Score type:** 0-1 continuous (fraction of hallucinated claims; 0.0 = no hallucination = best)

**Judge prompt:**

```
You are an expert fact-checker detecting hallucinations in a response. A hallucination is any claim in the response that is either contradicted by the retrieved context or fabricated (not present in the context at all). Your task is to determine what fraction of the response's claims are hallucinated.

## Inputs

**User query:**
{{ task_input }}

**Retrieved context (the only information the system had access to):**
{% for chunk in reference_data.retrieved_context %}
[Chunk {{ loop.index }}]: {{ chunk }}
{% endfor %}

**Response to evaluate:**
{{ final_message }}

## Instructions

Follow these steps precisely:

### Step 1: Extract claims
Break the response into individual, atomic factual claims. Each claim should be a single assertion that can be independently verified. Ignore meta-commentary, hedging phrases, and discourse markers.

If the response contains no factual claims (e.g., it is a refusal or purely a question), note this.

### Step 2: Classify each claim
For each extracted claim, classify it as:
- **Grounded**: The claim is directly stated in or logically entailed by the retrieved context.
- **Hallucinated (contradiction)**: The claim directly contradicts information in the retrieved context.
- **Hallucinated (fabrication)**: The claim introduces information not present in the retrieved context. This includes plausible-sounding facts, specific numbers, dates, or attributions that cannot be verified from the context.

Important: A claim based on common knowledge or general reasoning that is NOT in the retrieved context counts as a fabrication for this metric. The retrieved context is the only valid source of truth.

### Step 3: Calculate the hallucination score
Hallucination Score = (number of hallucinated claims) / (total number of claims).
If there are zero claims, the score is 0.0 (no hallucination).

Note: This score is INVERTED relative to Faithfulness. A score of 0.0 means no hallucination (best). A score of 1.0 means every claim is hallucinated (worst).

## Output format

Return your analysis as JSON with this exact structure:

{
  "claims": [
    {"claim": "<atomic claim text>", "classification": "grounded|hallucinated_contradiction|hallucinated_fabrication", "evidence": "<quote from context if grounded, or explanation of the contradiction/fabrication>"},
    ...
  ],
  "num_hallucinated": <integer>,
  "num_total": <integer>,
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<1-2 sentence summary of hallucination assessment>"
}
```

**Expected output format:** JSON object with `claims` array (each with `claim`, `classification` enum, `evidence`), `num_hallucinated`, `num_total`, `score` (float 0-1, where 0 is best), and `reasoning`.

**Edge cases the prompt handles:**
- **No claims in response:** Score is 0.0 (no hallucination detected). Consistent with Faithfulness template (which returns 1.0 for zero claims -- the two scores should sum to approximately 1.0 per claim set).
- **Contradictions vs. fabrications:** Both are classified as hallucination but the distinction is preserved in the `classification` field, allowing users to filter by type.
- **Partially correct claims:** A claim that is mostly correct but includes a fabricated detail (e.g., correct entity, wrong date) is classified as hallucinated. The `evidence` field explains the partial mismatch.
- **Common knowledge:** Treated as fabrication. The prompt explicitly states that the retrieved context is the only valid source.

**Relationship to Faithfulness:** For any given response, `Hallucination.score` should approximately equal `1.0 - Faithfulness.score`. They use the same claim-extraction methodology but report in opposite directions. Users can run both or either depending on their dashboard preferences. The templates are maintained independently to allow divergent evolution (e.g., Hallucination could add severity weighting in a future version without affecting Faithfulness).

**Validation strategy:**
- Cross-validate against Faithfulness template: for 50+ samples, verify that `Hallucination.score + Faithfulness.score` is within 0.05 of 1.0 (allowing for minor claim-extraction variance across independent runs).
- Hand-label 50 responses with known fabrications. Target: hallucinated claims detected with >= 85% precision and >= 75% recall.
- Compare against DeepEval's Hallucination metric on a shared dataset.

---

### 3.6. Answer Correctness

**Purpose:** Evaluate the factual accuracy and completeness of the model's output compared to a gold-standard reference answer. Unlike Faithfulness (which checks grounding in context), Answer Correctness checks whether the final answer is actually right, regardless of what context was available.

**Consumes reference keys:** `reference_answer`

**Score type:** 0-1 continuous

**Judge prompt:**

```
You are an expert evaluator assessing the factual correctness of a response by comparing it against a verified reference answer. Your task is to determine how accurate and complete the response is relative to the ground truth.

## Inputs

**User query:**
{{ task_input }}

**Reference answer (verified ground truth):**
{{ reference_data.reference_answer }}

**Response to evaluate:**
{{ final_message }}

## Instructions

Follow these steps precisely:

### Step 1: Extract key facts from the reference answer
Identify the essential factual assertions in the reference answer. These are the facts that a correct response MUST include or be consistent with. Distinguish between:
- **Core facts**: Central to answering the query. Missing these means the answer is fundamentally wrong or incomplete.
- **Supporting details**: Provide additional context or precision. Missing these reduces quality but does not make the answer wrong.

### Step 2: Check the response against each fact
For each fact from the reference answer, determine whether the response:
- **Matches**: States the fact correctly (exact match or semantically equivalent paraphrase).
- **Contradicts**: States something that conflicts with the fact.
- **Omits**: Does not mention the fact.

### Step 3: Check for fabricated content
Identify any claims in the response that are not present in the reference answer. Classify each as:
- **Correct elaboration**: True additional detail that is consistent with the reference (do not penalize).
- **Incorrect addition**: A false or misleading claim not supported by the reference (penalize).

### Step 4: Calculate the correctness score
Consider the following factors:
- Coverage of core facts (heaviest weight)
- Coverage of supporting details (moderate weight)
- Contradictions (heavy penalty)
- Incorrect additions (moderate penalty)
- Correct elaborations (no penalty)

Scoring guide:
- **1.0**: All core facts and most supporting details match. No contradictions. No incorrect additions.
- **0.7-0.9**: All core facts match. Minor omissions of supporting details or minor incorrect additions.
- **0.4-0.6**: Most core facts match but some are omitted or contradicted. Or significant incorrect additions.
- **0.1-0.3**: Few core facts match. Major contradictions or omissions.
- **0.0**: No core facts match or the response fundamentally contradicts the reference.

## Output format

Return your analysis as JSON with this exact structure:

{
  "reference_facts": [
    {"fact": "<fact from reference>", "type": "core|supporting", "status": "matches|contradicts|omits", "response_text": "<relevant quote from response, or null if omitted>"},
    ...
  ],
  "fabricated_content": [
    {"claim": "<claim not in reference>", "classification": "correct_elaboration|incorrect_addition"},
    ...
  ],
  "num_core_matched": <integer>,
  "num_core_total": <integer>,
  "num_contradictions": <integer>,
  "num_incorrect_additions": <integer>,
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<1-2 sentence summary of correctness assessment>"
}
```

**Expected output format:** JSON object with `reference_facts` array (each with `fact`, `type`, `status`, `response_text`), `fabricated_content` array (each with `claim`, `classification`), summary counts, `score` (float 0-1), and `reasoning`.

**Edge cases the prompt handles:**
- **Response is more detailed than reference:** Correct elaborations are not penalized. Only factually incorrect additions reduce the score.
- **Response uses different wording:** Semantic equivalence is accepted. The prompt asks for matching, not verbatim reproduction.
- **Partial answers:** A response that correctly addresses part of the query but omits major sections receives an intermediate score.
- **Multiple valid answers:** If the reference answer covers one valid interpretation but the response covers another equally valid interpretation, the judge should note this in reasoning. This is a known limitation -- the reference answer is treated as authoritative.
- **Empty response:** Score is 0.0 (no facts matched).

**Validation strategy:**
- Hand-label 50-100 query-reference-response triples with human correctness scores on a 5-point scale. Convert to 0-1 and compare against template scores. Target: Spearman rho >= 0.7.
- Compare against DeepEval's Answer Correctness metric and Braintrust's Answer Correctness scorer on a shared dataset.
- Include adversarial cases: responses that are confident and fluent but factually wrong.

---

## 4. Builder UX integration

Coordinate with Batch G (`components/70_builder_and_onboarding.md`):

- **RAG goal detection:** When the user selects "RAG evaluation" (or a synonymous goal like "evaluate my retrieval pipeline" or "check for hallucinations") in the builder questionnaire, the system should pre-populate a default EvalConfig set from this template library. Recommended defaults: Faithfulness + Answer Relevance + Context Relevance (the three that require only `retrieved_context`, which users are most likely to have).

- **Reference-key scaffolding:** When RAG templates are selected, the builder should auto-scaffold the expected reference keys on new EvalInputs. Specifically: prompt the user to populate `retrieved_context` (required for most RAG templates), and optionally `reference_answer` (if Answer Correctness is selected) and `ground_truth_context` (if Context Precision with ground truth is desired).

- **Guidance for populating `retrieved_context`:** The builder should include inline guidance: "Populate `retrieved_context` with the text chunks your RAG pipeline returned for each query. If you are using Langfuse, Phoenix, or another tracing tool, you can export retrieval results from production traces. For manual testing, paste the chunks directly." Production trace ingestion connectors (Langfuse, Phoenix) are out of scope for V2 but should be noted as a future integration point.

- **Template selection UI:** Each of the 6 templates should be selectable individually. The builder should show which reference keys each template requires so users understand the data requirements before committing.

---

## 5. Validation plan

### 5.1. Per-template golden datasets

For each of the 6 templates, build a hand-labeled golden dataset of 50-100 samples:
- **Faithfulness / Hallucination:** RAG responses with per-claim human labels (grounded/fabricated/contradicted).
- **Answer Relevance:** Query-response pairs with human relevance scores (5-point scale converted to 0-1).
- **Context Relevance:** Query-context pairs with per-chunk human relevance labels.
- **Context Precision:** Query-context pairs with per-chunk usefulness labels, half with ground truth context and half without.
- **Answer Correctness:** Query-reference-response triples with human correctness scores.

### 5.2. Correlation targets

- Primary metric: Spearman rank correlation between template scores and human labels.
- Target: rho >= 0.7 per template.
- Secondary: per-claim/per-chunk agreement rate >= 80% for claim-level and chunk-level templates (Faithfulness, Hallucination, Context Relevance, Context Precision).

### 5.3. Cross-tool benchmarking

- A/B test against DeepEval's RAG metrics (Faithfulness, Contextual Relevancy, Contextual Precision, Answer Correctness) on a shared dataset. Kiln templates should achieve comparable or better correlation with human labels.
- A/B test against Braintrust's autoevals RAG scorers (Faithfulness, Context Precision, Answer Relevancy, Answer Correctness) on the same dataset.
- Document any systematic divergences and explain them (e.g., differences in claim-extraction granularity, relevance thresholds).

### 5.4. RAGAS benchmark correlation

Where published RAGAS evaluation benchmarks exist (faithfulness, context recall), compare Kiln template scores against RAGAS scores on the same data. Note: RAGAS uses an NLI-based approach for some metrics; differences in methodology may explain score divergences. Document these.

### 5.5. Sign-off criterion

A template is ready to ship when:
1. Spearman rho >= 0.7 against human labels on the golden dataset.
2. No systematic failure modes identified in adversarial testing.
3. Cross-tool comparison shows no unexpected divergence from established implementations.

---

## 6. Open questions and dependencies

- **Default judge model (RESOLVED — Steve, 2026-06-06):** The claim-extraction templates (Faithfulness, Hallucination, Context Precision) want a capable judge model, but this needs **no enforcement and no new mechanism** — Kiln's existing model picker already steers users toward frontier-class models, which is the operative recommendation. `components/29` documents that these templates assume a capable judge (at or above Claude Sonnet 4 / GPT-4o tier) and degrade on small models; no hard gate. The judge model is the user's configured `llm_judge` model (`LlmJudgeProperties.model_name` / `.model_provider`). Phase 6's golden-dataset validation can sharpen the specific wording later.

- **Hallucination as separate template vs. `1 - Faithfulness`:** The design ships both as independent templates. Arguments for keeping both: (a) user expectations from DeepEval/LangSmith ecosystems, (b) the two metrics may evolve independently (e.g., Hallucination could add severity weighting), (c) inverted framing is more natural for defect dashboards. Arguments for collapsing: (a) redundant computation, (b) scores should sum to 1.0 and any divergence is confusing. Decision: ship both for V2.0; revisit if user feedback indicates redundancy is confusing.

- **Future composite "RAG score" rollup:** Multiple competitors (DeepEval's RAGAS composite, Promptfoo's derivedMetrics) offer a single composite RAG score. This is out of scope for V2.0 -- it requires the `composite` EvalConfigType (deferred to Phase 7 per A2.4). Note as a Phase 7 candidate.

- **Embedding-based metrics:** Answer Similarity (embedding cosine similarity between output and reference) and Context Recall (embedding-based overlap between retrieved context and ground truth context) are deferred to Phase 7 with the `embedding_similarity` EvalConfigType. These require embedding model infrastructure that the `llm_judge` type does not provide.

- **Template variable rendering (O-rag-template-var-rendering — RESOLVED 2026-06-06):** Supported as-is, no schema or engine change. The `llm_judge` template engine is Jinja2 `SandboxedEnvironment` (`components/06` section, shared via `libs/core`). `{% for chunk in reference_data.retrieved_context %}` and `{{ loop.index }}` are core Jinja2 control structures — the sandbox restricts only unsafe attribute/builtin access, not iteration over a `list[str]`. No pre-formatting needed. **Authoring rule (added):** each template must declare its required reference keys (e.g. `retrieved_context`) in the EvalConfig's `required_var` list, so a missing key produces a clean pre-render *skip* (`extraction_failed` / `missing_reference_key`, per C.runner.1) rather than a hard `StrictUndefined` error at render time. Optional keys (e.g. `ground_truth_context`) stay guarded by `{% if reference_data.<key> %}` and are omitted from `required_var`.

- **Claim extraction consistency:** Faithfulness and Hallucination both perform claim extraction independently. Two independent judge calls on the same response may extract slightly different claim sets. This is acceptable (each template is a standalone eval) but may cause `Faithfulness.score + Hallucination.score` to deviate slightly from 1.0. Document this expected variance.

---

## 7. Out of scope for this doc

- **Embedding-based metrics** (Answer Similarity, embedding-enhanced Context Recall) -- deferred to Phase 7 with `embedding_similarity` type.
- **End-to-end retrieval execution** -- users supply `retrieved_context` at EvalInput creation time. Kiln does not run the retriever.
- **RAGAS-style composite score** -- deferred to Phase 7 with `composite` type.
- **Production trace ingestion** -- Steve has declined this for V2 (out of scope entirely). Users import context manually or via external tooling.
- **Multi-turn RAG evaluation** -- these templates evaluate single-turn RAG interactions. Multi-turn RAG (conversational retrieval) is a separate design concern tied to `MultiTurnSyntheticEvalInputData`.
- **Custom RAG metrics** -- users who need metrics beyond these 6 can author custom `llm_judge` prompts using the same reference-key contract. No special framework needed.

---

## Opens

None. All previously-tracked opens resolved at Stage 5 (2026-06-06):

- **(O-rag-template-var-rendering)** RESOLVED — sandboxed Jinja2 supports `{% for %}` iteration over `reference_data` list sub-paths; no pre-formatting. See section 6 "Template variable rendering" for the resolution + the `required_var` authoring rule.
- **(O-rag-min-judge-model)** RESOLVED (Steve) — documented recommendation only (capable/frontier-class judge); Kiln's existing model picker already steers users to frontier models. No gate. See section 6 "Default judge model."
- **RAG Quick Start guide** RESOLVED — not a V2.0 design blocker; rely on the builder UX (section 4) to surface the workflow. A standalone quick-start guide is an optional docs-time nice-to-have, not a design dependency.
- **Missing-required-key behavior** RESOLVED — clean *skip* (not fail-hard), via the `required_var` pre-check that skips with `extraction_failed` / `missing_reference_key` before render (C.runner.1 / `components/45`). Captured by the authoring rule in section 6.
- [ ] Whether `ground_truth_context` should be promoted to required (not optional) for Context Precision, or whether the fallback mode (query-only usefulness) is valuable enough to keep.
