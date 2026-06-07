"""Pre-built RAG evaluation judge templates.

Each factory function returns a fully configured ``LlmJudgeProperties``
with a Jinja2 prompt template targeting a specific RAG quality dimension.
The templates reference fields from ``EvalTaskInput.model_dump()`` namespace:
``final_message``, ``trace``, ``reference_data``, ``task_input``.
"""

from kiln_ai.datamodel.eval import LlmJudgeProperties

_FAITHFULNESS_PROMPT = """\
You are evaluating whether the answer is faithful to the provided context. \
An answer is faithful if every claim it makes is supported by the context.

## Question
{{ task_input }}

## Retrieved Context
{% for chunk in reference_data.retrieved_context %}[Chunk {{ loop.index }}]: {{ chunk }}
{% endfor %}

## Answer
{{ final_message }}

## Instructions
1. Identify each distinct factual claim in the answer.
2. For each claim, determine whether it is directly supported by the retrieved context.
3. Calculate the faithfulness score as: num_supported / num_total (if there are 0 claims, score 1.0).

Respond with a JSON object using this exact structure:
```json
{
  "claims": [{"claim": "<text>", "supported": true, "evidence": "<quote or null>"}],
  "num_supported": <int>,
  "num_total": <int>,
  "score": <float 0-1>,
  "reasoning": "<1-2 sentence summary>"
}
```\
"""

_ANSWER_RELEVANCE_PROMPT = """\
You are evaluating whether the answer is relevant to the question asked.

## Question
{{ task_input }}

## Answer
{{ final_message }}

## Instructions
1. Read the question carefully and identify what is being asked.
2. Evaluate whether the answer directly addresses the question.
3. Consider completeness: does the answer cover the key aspects of the question?
4. Consider conciseness: does the answer stay on topic without excessive irrelevant information?
5. Score on a continuous 0-1 scale: 1.0 = directly addresses the query with complete and concise coverage; 0.0 = completely irrelevant.

Respond with a JSON object using this exact structure:
```json
{
  "user_intent": "<summary of what user is asking>",
  "addresses_question": "<assessment>",
  "completeness": "<assessment>",
  "conciseness": "<assessment>",
  "score": <float 0-1>,
  "reasoning": "<1-2 sentence summary>"
}
```\
"""

_CONTEXT_RELEVANCE_PROMPT = """\
You are evaluating whether the retrieved context is relevant to the question.

## Question
{{ task_input }}

## Retrieved Context
{% for chunk in reference_data.retrieved_context %}[Chunk {{ loop.index }}]: {{ chunk }}
{% endfor %}

## Instructions
1. Read the question and understand what information is needed to answer it.
2. Examine each retrieved context chunk.
3. For each chunk, determine whether it contains information relevant to answering the question.
4. Calculate the relevance score as: num_relevant / num_total.

Respond with a JSON object using this exact structure:
```json
{
  "information_need": "<summary of what info is needed>",
  "chunk_evaluations": [{"chunk_index": 1, "relevant": true, "reason": "<why>"}],
  "num_relevant": <int>,
  "num_total": <int>,
  "score": <float 0-1>,
  "reasoning": "<1-2 sentence summary>"
}
```\
"""

_CONTEXT_PRECISION_PROMPT = """\
You are evaluating context precision: whether the retrieved context chunks \
are useful for producing a correct answer to the question.

## Question
{{ task_input }}

## Retrieved Context
{% for chunk in reference_data.retrieved_context %}[Chunk {{ loop.index }}]: {{ chunk }}
{% endfor %}
{% if reference_data.ground_truth_context %}
## Ground Truth Context (for comparison)
{% for chunk in reference_data.ground_truth_context %}[Ground Truth {{ loop.index }}]: {{ chunk }}
{% endfor %}
{% endif %}

## Instructions
1. Read the question and understand what information is needed.
2. Examine each retrieved context chunk and determine whether it is useful for producing a correct answer.
{% if reference_data.ground_truth_context %}\
3. Compare against the ground truth context to assess precision.
{% endif %}\
4. Calculate the precision score as: num_useful / num_total.

Respond with a JSON object using this exact structure:
```json
{
  "mode": "{% if reference_data.ground_truth_context %}with_ground_truth{% else %}without_ground_truth{% endif %}",
  "chunk_evaluations": [{"chunk_index": 1, "useful": true, "reason": "<why>"}],
  "num_useful": <int>,
  "num_total": <int>,
  "score": <float 0-1>,
  "reasoning": "<1-2 sentence summary>"
}
```\
"""

_HALLUCINATION_PROMPT = """\
You are evaluating whether the answer contains hallucinated information. \
A hallucination is any statement that is not supported by or contradicts the provided context. \
A higher score means MORE hallucination (worse). 0.0 = no hallucination (best).

## Question
{{ task_input }}

## Retrieved Context
{% for chunk in reference_data.retrieved_context %}[Chunk {{ loop.index }}]: {{ chunk }}
{% endfor %}

## Answer
{{ final_message }}

## Instructions
1. Identify each distinct factual claim in the answer.
2. For each claim, classify it as "grounded" (supported by context), \
"hallucinated_contradiction" (contradicts context), or "hallucinated_fabrication" \
(not mentioned in context at all).
3. Calculate the hallucination score as: num_hallucinated / num_total \
(if there are 0 claims, score 0.0 since there are no hallucinations).

Respond with a JSON object using this exact structure:
```json
{
  "claims": [{"claim": "<text>", "classification": "grounded|hallucinated_contradiction|hallucinated_fabrication", "evidence": "<explanation>"}],
  "num_hallucinated": <int>,
  "num_total": <int>,
  "score": <float 0-1>,
  "reasoning": "<1-2 sentence summary>"
}
```\
"""

_ANSWER_CORRECTNESS_PROMPT = """\
You are evaluating factual correctness by comparing the model's answer \
against a reference answer.

## Question
{{ task_input }}

## Reference Answer
{{ reference_data.reference_answer }}

## Model Answer
{{ final_message }}

## Instructions
1. Identify the key facts in the reference answer, classifying each as "core" \
(essential to a correct answer) or "supporting" (helpful but not essential).
2. For each reference fact, check whether it is present and accurate in the \
model's answer: "matches", "contradicts", or "omits".
3. Identify any claims in the model's answer not present in the reference, \
classifying them as "correct_elaboration" or "incorrect_addition".
4. Calculate the correctness score as a weighted 0-1 float based on core-fact \
coverage, contradictions, and incorrect additions. 1.0 = fully correct, 0.0 = \
completely incorrect.

Respond with a JSON object using this exact structure:
```json
{
  "reference_facts": [{"fact": "<text>", "type": "core|supporting", "status": "matches|contradicts|omits", "response_text": "<quote or null>"}],
  "fabricated_content": [{"claim": "<text>", "classification": "correct_elaboration|incorrect_addition"}],
  "num_core_matched": <int>,
  "num_core_total": <int>,
  "num_contradictions": <int>,
  "num_incorrect_additions": <int>,
  "score": <float 0-1>,
  "reasoning": "<1-2 sentence summary>"
}
```\
"""


def faithfulness_template(model_name: str, model_provider: str) -> LlmJudgeProperties:
    """Template for evaluating answer faithfulness to provided context."""
    return LlmJudgeProperties(
        model_name=model_name,
        model_provider=model_provider,
        system_prompt="You are an expert fact-checker evaluating whether a response is faithful to its source context.",
        prompt_template=_FAITHFULNESS_PROMPT,
        required_var=["reference_data.retrieved_context"],
        thinking_instruction="Think step by step about whether each claim in the answer is supported by the provided context.",
        g_eval=False,
    )


def answer_relevance_template(
    model_name: str, model_provider: str
) -> LlmJudgeProperties:
    """Template for evaluating answer relevance to the question."""
    return LlmJudgeProperties(
        model_name=model_name,
        model_provider=model_provider,
        system_prompt="You are an expert evaluator assessing whether responses are relevant to user queries.",
        prompt_template=_ANSWER_RELEVANCE_PROMPT,
        required_var=["task_input"],
        thinking_instruction="Think step by step about whether the response addresses the user's query, considering relevance, completeness, and conciseness.",
        g_eval=False,
    )


def context_relevance_template(
    model_name: str, model_provider: str
) -> LlmJudgeProperties:
    """Template for evaluating retrieved context relevance to the question."""
    return LlmJudgeProperties(
        model_name=model_name,
        model_provider=model_provider,
        system_prompt="You are an expert evaluator assessing retrieval quality in RAG systems.",
        prompt_template=_CONTEXT_RELEVANCE_PROMPT,
        required_var=["task_input", "reference_data.retrieved_context"],
        thinking_instruction="Think step by step about whether each retrieved chunk contains information relevant to answering the user's query.",
        g_eval=False,
    )


def context_precision_template(
    model_name: str, model_provider: str
) -> LlmJudgeProperties:
    """Template for evaluating whether relevant context is ranked higher."""
    return LlmJudgeProperties(
        model_name=model_name,
        model_provider=model_provider,
        system_prompt="You are an expert evaluator assessing retrieval precision in RAG systems.",
        prompt_template=_CONTEXT_PRECISION_PROMPT,
        required_var=["task_input", "reference_data.retrieved_context"],
        thinking_instruction="Think step by step about whether each retrieved chunk is useful for producing a correct answer to the user's query.",
        g_eval=False,
    )


def hallucination_template(model_name: str, model_provider: str) -> LlmJudgeProperties:
    """Template for detecting hallucinated content in answers."""
    return LlmJudgeProperties(
        model_name=model_name,
        model_provider=model_provider,
        system_prompt="You are an expert evaluator detecting hallucinations in RAG system outputs.",
        prompt_template=_HALLUCINATION_PROMPT,
        required_var=["reference_data.retrieved_context"],
        thinking_instruction="Think step by step about whether each claim in the answer is grounded in the retrieved context, contradicts it, or is fabricated.",
        g_eval=False,
    )


def answer_correctness_template(
    model_name: str, model_provider: str
) -> LlmJudgeProperties:
    """Template for evaluating factual correctness against a reference answer."""
    return LlmJudgeProperties(
        model_name=model_name,
        model_provider=model_provider,
        system_prompt="You are an expert evaluator assessing the factual correctness of responses against reference answers.",
        prompt_template=_ANSWER_CORRECTNESS_PROMPT,
        required_var=["reference_data.reference_answer", "task_input"],
        thinking_instruction="Think step by step about the factual correctness of the response compared to the reference answer, checking for matches, contradictions, omissions, and fabricated content.",
        g_eval=False,
    )
