---
description: >-
  Know your Kiln Search tools find the right answer with RAG evals and synthetic
  Q&A data
online_url: https://docs.kiln.tech/docs/evals-and-specs/evaluate-rag-accuracy-q-and-a-evals
---

# Evaluate RAG Accuracy: Q\&A Evals

{% hint style="success" %}
**Evaluating RAG is tricky**. An LLM-as-judge doesn't have the knowledge from your documents, so it can't tell if a response is actually correct. But giving the judge access to RAG biases the evaluation.&#x20;

**The solution** is reference-answer evals. The judge compares results to a known correct answer. Building these datasets used to be a long manual process, but Kiln makes the process fast and easy.
{% endhint %}

#### Overview

Reference answer accuracy evals measure how well your model leverages search tools (RAG) by generating query-answer (Q\&A) pairs from your document library and using them as reference answers to test your RAG system's responses. This approach includes:

* Generating large eval datasets quickly from your existing documents using synthetic Q\&A pair generation
* Creating realistic queries that reflect user questions about your corpus
* Using reference answers (ground truth) derived from your documents to evaluate accuracy
* Systematically testing different search tool configurations (chunking strategies, embedding models, etc.) and task models to find optimal settings

### Video Preview

{% embed url="https://vimeo.com/1137040663" %}

### The Workflow

This guide walks through the RAG-specific workflow for reference answer accuracy evals:

* Creating a Reference Answer Accuracy Eval
* Generating Q\&A pairs from your documents
* Setting up a Judge
* Finding the Ideal Run Configuration

For general eval concepts like judges, run configurations, and comparing results, see Evaluations.

### Creating a Reference Answer Accuracy Eval

From the "Eval" tab in Kiln's UI, create a new evaluator using the "Reference Answer Accuracy Eval (RAG)" template.

{% hint style="info" %}
**Reference Answer Accuracy Eval (RAG)**: This template is designed for evaluating Q\&A pairs and includes a Reference Answer Accuracy score (pass/fail) that evaluates if the model's output is accurate as per the reference answer. The template is configured to work with Q\&A datasets built from your documents.
{% endhint %}

Select the template, edit if desired, and save your eval.

### Generate Q\&A Pairs

Most commonly, you'll want to populate your eval dataset using synthetic Q\&A pairs generated from your documents. These pairs include reference answers that serve as ground truth for evaluation. Clicking "Add Eval Data" from the Evals UI, and selecting "Synthetic Data" will launch the Q\&A generation tool with the proper eval tags already populated.

#### Select Documents

Choose which documents from your library to use for generating Q\&A pairs:

* **All documents**: Use every document in your library
* **Filter by tags**: Select specific documents by applying tag filters. This is useful when you want to generate evals for a specific subset of your corpus.

You can add tags to documents in the Document Library UI (found in the Docs & Search tab) to organize them for filtering.

#### Extract Documents

Before generating Q\&A pairs, you need to extract text from your documents. Choose an extractor config that will process your documents. The extractor converts your documents (PDFs, HTML, etc.) into markdown or plain text. If you've already extracted documents with this extractor, those extractions will be reused.

#### Generate Pairs

Configure the generation process to create Q\&A pairs from your documents.

**Generation Settings**

* **Pairs per document/chunk**: How many Q\&A pairs to generate from each document/chunk. More pairs give you a larger eval dataset but take longer to generate.
* **Model and provider**: The AI model used to generate Q\&A pairs. Larger models typically produce higher quality pairs.
* **Guidance**: Optional instructions to steer the generation. You can:
  * Use the default Q\&A generation template (recommended for most cases)
  * Provide custom guidance to focus on specific types of queries (e.g. "Focus on technical questions")

<details>

<summary>Optional: Break Long Documents Into <strong>Chunks</strong></summary>

Under "Advanced Options", check the "Split documents into smaller chunks" checkbox if you want to split documents before generating pairs. This is recommended for very long documents such as books, manuals, or transcripts. Splitting into smaller chunks helps create more focused Q\&A pairs.

* **Chunk size (tokens)**: The maximum size of each chunk. Smaller chunks create more focused Q\&A pairs but may miss context that spans chunks.
* **Chunk overlap (tokens)**: How much text overlaps between adjacent chunks. Overlap helps preserve context at chunk boundaries.

If you leave it unchecked, Q\&A pairs will be generated from entire documents without chunking. This works well for shorter documents or when you want queries that span the full document context.

**Generation Settings**

* **Pairs per document/chunk**: How many Q\&A pairs to generate from each document/chunk. More pairs give you a larger eval dataset but take longer to generate.
* **Model and provider**: The AI model used to generate Q\&A pairs. Larger models typically produce higher quality pairs.
* **Guidance**: Optional instructions to steer the generation. You can:
  * Use the default Q\&A generation template (recommended for most cases)
  * Provide custom guidance to focus on specific types of queries (e.g. "Focus on technical questions")

</details>

**What Gets Generated**

* **Queries**: Realistic questions that users might ask about your document corpus. These can be:
  * Natural language questions (e.g. "What is the population of Pittsburgh?")
  * Search-style queries (e.g., "Pittsburgh population 2020")
* **Reference Answers**: Factual, concise answers derived from the document content. These serve as ground truth for evaluating your RAG system's accuracy.

#### Review and Save

* Review generated pairs organized by document/chunk
* Remove individual pairs, entire chunks or documents if needed
* Click "Save All" to save the Q\&A pairs to your dataset.

Since these pairs contain reference answers, there's no need for a separate golden set. All pairs should be tagged with your eval tag (typically starting with `qna_eval_set`).

Pairs will also be saved with tags that identify:

* They're synthetic Q\&A data (`synthetic`, `qna`)
* Their generation session ID (starting with `synthetic_qna_session`)

### Setting up a Judge

Before evaluating different run configurations, you need to create a judge. The eval you created defines the goal, but the judge defines how it's run (judge algorithm, model, and instructions).

Click "Create Judge" to get started. For detailed guidance on selecting judge algorithms (LLM as Judge vs G-Eval), models, and customizing evaluation steps, see Add a Judge section.

### Finding the Ideal Run Configuration

Once you have a judge set up, you can evaluate different configurations for running your RAG task. You can test different task models, prompts, and model parameters to find the best combination for answering questions from your document corpus. For detailed guidance on selecting and comparing task model options, see Finding the Ideal Run Method.

Since reference answer accuracy evals specifically test how well your RAG system retrieves and uses information from your documents, you'll also want to test different search tool configurations:

* A range of extraction models
* Different chunking strategies: fixed window or semantic, with varying chunk sizes and overlap
* A range of embedding models for search
* Different search index configurations: full-text search, vector search, or hybrid search, with varying K values
* A range of reranking models, with varying N top results

Once you've defined a set of run configurations (combining different task model options and search tool configurations), click "Run Eval" to test them against your Q\&A dataset.

<a href="references/docs/documents-and-search-rag.md#optimizing-your-rag" class="button primary">RAG Optimization Guide</a>

**Comparing Results**

After the eval completes, you'll see average scores for each run configuration. The highest average score indicates the best-performing configuration for your RAG system.

This systematic approach helps you find the optimal combination of task model and Search Tool settings for answering questions from your document corpus.
