---
description: Add knowledge to your AI systems with docs & search
icon: magnifying-glass
online_url: https://docs.kiln.tech/docs/documents-and-search-rag
---

# Documents & Search (RAG)

RAG (Retrieval-Augmented Generation) is a powerful technique for adding knowledge to AI systems, and Kiln makes building RAG systems incredibly easy!

### Quick Start: Create a RAG in Under 5 Minutes

Building a search tool in Kiln takes 3 steps:

1. [Adding Documents](references/docs/documents-and-search-rag.md#adding-documents): Drag and drop files into the Kiln document library
2. [Create a search tool](references/docs/documents-and-search-rag.md#building-a-search-tool): specify how you want Kiln to search the documents
3. [Use the tool](references/docs/documents-and-search-rag.md#using-search-tools): Select the search tool when running your task

See our Video Guide if you prefer video format:

{% embed url="https://vimeo.com/1138141451" %}

### Document Library

You can open the document library from the “Manage Documents” link in the “Docs & Search” tab.

#### Adding Documents

To add documents, simply click “Add Documents” in the Document Library, then drag-and-drop in as many files as you like.

{% hint style="info" %}
Documents are added to your Kiln project; if you’re using Kiln to [collaborate with a team](references/docs/collaboration/), documents will be available to everyone.
{% endhint %}

#### Supported File Types

Kiln supports the following file types:

* **Documents**: .pdf, .txt, .md, .html
* **Images**: .jpg, .jpeg, .png
* **Videos**: .mp4, .mov
* **Audio**: .mp3, .wav, .ogg

{% hint style="info" %}
Not every extraction model can handle every file type. Use Google Gemini models for maximal file type support. When creating a custom search tool, the model selection dropdown will list supported file types.
{% endhint %}

#### Tagging Documents

Documents can be organized by adding tags. This is typically used to sub-divide your docs library into sections, which allows you to build search tools targeting specific document sets. Here are some examples:

* **knowledge\_base**: your public help docs / knowledge base
* **customer\_support\_policies**: internal docs for how to respond to various types of customer requests
* **product\_specs**: feature definitions, product requirement docs, spec sheets
* **blog\_posts**: your company’s blog posts

You can add or remove tags in Kiln in 2 ways:

1. Single document: open a document’s page in the document library, then add or remove tags using the “Tags” sidebar.
2. Many documents: click “select” in the document library, select all relevant documents, click the tag icon, then select “Add Tags” or “Remove Tags”

### Building a Search Tool

Once you’ve added documents, you can create a search tool in a few clicks!

#### Suggested Search Configurations

If you're new to building RAG systems, we strongly recommend selecting one of the suggested search configurations to start. These are high quality RAG setups that can give you state of the art performance. Simply select one of the following templates from "Docs & Search" > "Manage Search Tools" > "Add Search Tool":

* **Best Quality**: The best quality search configuration we’ve found. Uses Gemini 2.5 Pro to extract documents to text.
* **Cost Optimized**: Still excellent, but lower cost. This configuration uses Gemini 2.5 Flash to extract documents to text.
* **Vector Only**: A configuration which only uses vector search for semantic similarity, without keyword search. Useful when you want to search only on semantic meaning without weighing the keywords in the query.
* **OpenAI Based**: We suggest using a Gemini-powered config above if possible — they support more document types and have better document extraction quality. However, if you are required to use OpenAI APIs, try this configuration with GPT-4o. This config does not support transcribing audio and video.

We’re working on adding more document extractors and embedding providers to expand this list.

#### Search Tool Name & Description

When you’re creating a search tool, you’ll be asked to provide a tool name and description. These are important as the model will read them to decide if and when to use your search tool.

For example:

* **Poor:** search\_tool - “Search documents for knowledge”
* **Better:** doc\_search - “Search the knowledge base for product information”
* **Best:** knowledge\_base\_search - "Search Kiln's user-facing documents, guides, and walkthroughs."

In the first example, the model will have no idea what type of documents it has access to, or if/when to search them. The last example is much better; from it the model knows what the documents are, the audience they are written for, and can infer when searching them would be helpful to a task.

#### Custom Search Configurations

If you have experience with RAG systems, you can create a completely custom RAG. Simply select “Create Custom” on the “Add Search Tool (RAG)” screen.

{% hint style="warning" %}
**Advanced Users Only**: unless you have experience with AI embeddings and search, we suggest sticking to the suggested search tool configurations.
{% endhint %}

You can customize:

* Extractor: The model used to extract non-text documents (e.g. PDFs, videos) into text. Optionally customize the prompts passed to the extractor model for each type of file.
* Chunking Strategy: specify how large documents are split into smaller chunks for embedding, indexing, and retrieval
* Embeddings: specify the embedding model and embedding dimensions
* Search Index / Vector Store: select the search index strategy including vector index, full-text search, or hybrid mode.

Want to see more options here? Let us know on our [Discord](https://kiln.tech/discord)!

#### Processing Documents

After adding documents, Kiln must process them before they can be searched. You can monitor progress on the "Search Tools (RAG)" page. See [how it works](references/docs/documents-and-search-rag.md#how-it-works) below for more information about what each step is doing.

### Using Search Tools

Once you’ve [created a search tool](references/docs/documents-and-search-rag.md#building-a-search-tool) and [processing is complete](references/docs/documents-and-search-rag.md#processing-documents), you can run your search tools!

#### Using a Search Tool in a Task

To use a search tool in a task, simply select it from the “Tools” dropdown in the “Advanced” section of the Run page then run your task.

The search tool will be provided to your task, and your model may invoke it. You can view the model’s tool calls and the search tool’s response in the “All Messages” section of the run page:

{% hint style="info" %}
It’s the model’s choice if and when to invoke a tool. If the model isn’t invoking search when you feel it should, see the section below on [optimizing your RAG](references/docs/documents-and-search-rag.md#step-1-optimize-search-tool-name-description-and-task-prompt).
{% endhint %}

#### Testing Your Search Tool

If you just want to test your tool to see what it returns, you can do so from "Docs & Search" > "Search Tools" > search tool details. Enter any query to see what your search tool returns.

This mode is intended only for testing. It will render the raw chunks as would be returned to the AI task. You wouldn't normally expose these results directly to a user, and instead would have an AI task extract answers or summarize the content.

### How it Works

Under the hood, there are 4 stages to Kiln's RAG/search pipeline:

1. Document Extraction: convert documents like PDFs, videos, and audio into text data that language models can read.
2. Chunking: break down large documents into smaller chunks
3. Embedding: generate semantic embeddings from your chunks
4. Search: index the embeddings and chunks in a vector database, then search it

### Optimizing your RAG

Kiln offers several options for improving your RAG. To do so, you can create multiple search tools, then compare their quality using either:

* Manually review search result quality in the [search tool test UI](references/docs/documents-and-search-rag.md#testing-your-search-tool)
* Write [evals](references/docs/evals-and-specs/evaluations.md) to measure resulting task quality

{% hint style="success" %}
Kiln will minimize processing where possible. For example, if many search tools all share the same extraction config, it will reuse the prior extractions. This makes experimentation faster and reduces costs.
{% endhint %}

#### Step 1: Optimize Search Tool Name, Description and Task Prompt

Often we see issues where the search tool can easily retrieve the needed data, but the tool is never called. This is easy to identify: check the "All Messages" section of the run to see if the tool was invoked.

This is usually an easy fix with one of the following:

* Make the search tool name and description more descriptive: [example and guidance](references/docs/documents-and-search-rag.md#search-tool-name-and-description).
* Make the task's prompt explicitly define when search tools should be used, for example by adding "Always confirm answers with the knowledge\_base\_search tool."

#### Step 2: Improve Document Extraction

The first step of RAG is extracting your documents (PDFs, images, videos) into text which we can index, search, and provide to tasks after retrieval.

{% hint style="info" %}
If the data produced during extraction isn’t high quality, there’s nothing the rest of the pipeline can do to recover.
{% endhint %}

Walk through these steps to identify and improve document extraction:

1. **Inspect Extractions for Issues**: Read document extractions and compare with the original documents. You can do this by clicking on documents in the document library. Once you identify issues, you can fix them using the steps below. Example issues:
   * Including irrelevant data, like a header/footer content, transcribing menus/navigation content, or transcriptions of images which are embedded but not part of the core content (navigation, headers, even web ads).
   * Skipping important data, like insights from chart images
2. **Upgrade Extraction Model**: If you have issues, consider a higher quality extraction method. Often a better model will resolve extraction issues. We suggest trying Gemini 2.5 Pro via the Gemini API. While these APIs can be costly, you only need to extract documents once so it’s not a recurring cost.
3. **Customize Extraction Prompts \[Video Example Below]**: The default extraction prompts in Kiln are generalized prompts designed to work with any document. However, if you know your documents are a specific format, you can improve extraction by creating custom extraction prompts for your use case. You can do this when creating a new Search Tool, in the “Advanced section” of the extractor. See the demo video and the "Custom Extraction Prompt Examples" section below for details.
4. **Fully Custom Extraction**: If desired, you can always extract your documents separately using your own code, then add text (`.txt`) or markdown (`.md`) files to Kiln. This gives you complete control. Kiln won’t re-process files that are already in text/markdown formats.

{% embed url="https://vimeo.com/1138970149" %}

<details>

<summary>Custom Extraction Prompt Examples</summary>

Here is an example prompt if you know all documents are PDFs of blog posts:

{% code overflow="wrap" %}
```
Only transcribe the blog title, subtitle, byline and blog post content.

Ignore other elements of the page including headers, footers, and navigation elements.

Extract the blog data into markdown. Specify the post title as H1 (`#`) at the top, and all section titles should be smaller (H2, H3, etc).
```
{% endcode %}

Example for extracting invoices:

{% code overflow="wrap" %}
````
You are extracting invoice PDFs. Only extract payee, payer, date, status, invoice number, and invoice line items. Disregard headers, footers, addresses, and decorative elements.

Extract the invoice data into the following format:
```
Payee Name: X
Invoice ID: X
...
```
````
{% endcode %}

{% hint style="info" %}
Videos, Documents and Audio have separate prompts, so you can customize each to the use case as needed.
{% endhint %}

</details>

#### Step 3: Tune Chunking Size and Top-K

When your task calls your search tool, it will fetch a certain number of document chunks. Chunks are created by splitting long documents into smaller pieces. This is important for 2 reasons:

* You don’t want to feed too much information into the task, as it will flood the context, produce poorer results, and cost more.
* Splitting into chunks improves search relevance. A 50 page document might contain information on many topics. Searching for smaller chunks reduces the topic per segment, which helps your search tool find the most relevant portions of the document.

{% hint style="info" %}
The chunk size is defined when creating a search tool, in the chunking method options. You can also define how much overlap there is between chunks. The default is 512 words/tokens per chunk with 64 words/tokens overlap.

The number of results returned is called top-k, and is defined when creating a search tool, in the search index options. The default is to return 10 chunks.
{% endhint %}

Tuning these two variables for your use case can help produce better search results.

**Option 1: Increase Chunk Size and Reduce Top-K** Sometimes you know there’s exactly one document which will contain the answer; for example for the question “What is the total on invoice INV-123456?”. Returning 10 invoices won’t help this query, and will splitting the one invoice across 5 chunks could harm its performance. In this case, a larger chunk size and a small top-K would be a great configuration. You’ll still end up returning a reasonable amount of data, as you’ve lowered top-K.

**Option 2: Lower Chunk Size and Increase Top-K** Sometimes you know the model will need many of chunks to get a good answer; for example “Which protein structures were rated as ‘promising’ in experiments from June to July 2025?” might need to return hundreds of data chunks. In this case a small chunk size and higher top-K could work well.

{% hint style="info" %}
It's almost never a good idea to set Top-K to 1. There's always a chance that an answer is split across 2 or more chunks, so returning multiple chunks is always a good idea.
{% endhint %}

#### Step 4: Tune Search Index Options

Kiln has powerful search options, backed by [LanceDB](https://lancedb.com/):

* **Vector Search**: Searches for chunks based on an embedding/vector representation of their semantic meaning. This lets you find results that _mean_ the same thing, even if the query uses completely different wording.
* **Full-text search (aka keyword search or BM25)**: Searches for literal words/terms. It scores chunks based on how often your keywords appear (term frequency) and how rare they are across the entire dataset (inverse document frequency).
* **Hybrid search**: Combines both vector and full-text search, giving you relevance by meaning _and_ by exact keyword match.

{% hint style="info" %}
Vector and Hybrid search require calculating an embedding of the search query. This requires calling an embedding model which can take time, and cost money if using a paid API.
{% endhint %}

You can read more about search indexing and retrieval in the [LanceDB docs](https://www.lancedb.com/docs/search/) or on the [LanceDB Blog](https://blog.lancedb.com/hybrid-search-combining-bm25-and-semantic-search-for-better-results-with-lan-1358038fe7e6/).

We typically recommend **hybrid search**, but your use case might benefit from other options:

* **Full-text only**: best for cases where you want _exact term matching_ (e.g. legal text search, log file search), or extremely fast performance.
* **Vector-only**: best for cases where _meaning matters more than exact words_ (e.g. semantic question answering, summarization datasets).
* **Hybrid**: best for cases where you want both — i.e. match the meaning but still boost exact matches.

#### Step 5: Explore Embedding Models

As a last step, you can try different embedding models: the models which generate a embedding/vector-representation from a chunk.

Generally, we suggest exhausting the options above before tuning here.

### Deploying your RAG

Once you've optimized your RAG in Kiln, you're ready to deploy it!

You have several deployment options to choose from, depending on your use case:

#### **Kiln UI: For Personal Use**

You can continue to use the Search Tool inside Kiln, using the "Run" UI. This option is great for a single user or small teams. See our [collaboration docs](references/docs/collaboration/) for how to share a search tool with your team.

#### **MCP: For Local LLM Clients**

If you prefer another LLM frontend like LMStudio or Jan, you can run your Kiln Search Tool as an MCP server, then connect to it from your client of choice. See our [MCP server documentation for instructions](https://github.com/Kiln-AI/Kiln/tree/main/libs/server/kiln_server/mcp#readme) on running an MCP server exposing Kiln Search Tools.

#### **LlamaIndex: For Production Applications**

You can load your Kiln RAG dataset into a production-ready [LlamaIndex](https://www.llamaindex.ai/) stack. See our [Python library docs](https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai.html#taking-kiln-rag-to-production) for how to load a Kiln Search Tool into any LlamaIndex vector store.

<a href="https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai.html#taking-kiln-rag-to-production" class="button primary">Deploy a Kiln Search Tool</a>

_**We recommend**_ [_**LanceDB Cloud**_](https://lancedb.com/) _**for production hosting**_. The Kiln app and library use LanceDB; using LanceDB in prod ensures your production stack matches the RAG you optimized in Kiln perfectly. It is a performant vector database for any scale.

{% hint style="success" %}
Note: Loading a production index will not need to repeat extraction, chunking, and embeddings. Those steps are already completed in Kiln, and their results are saved in your Kiln dataset.
{% endhint %}
