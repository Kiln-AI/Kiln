# Documents API

Manage documents, extraction, chunking, embedding, vector stores, and RAG configurations.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/documents/bulk`|POST|Bulk Create Documents|Upload files to the project's document library, as multipart form data.|post_api_projects_project_id_documents_bulk.md|
|`/api/projects/{project_id}/documents`|GET|List Documents|List the documents in the project's library, optionally only those with given tags.|get_api_projects_project_id_documents.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}/extractions`|GET|List Extractions for Extractor Config|Return mapping of document id to list of extractions for the given extractor config id.|get_api_projects_project_id_extractor_configs_extractor_config_id_extractions.md|
|`/api/projects/{project_id}/documents/tags`|GET|List Document Tags|List the tags used on the project's documents.|get_api_projects_project_id_documents_tags.md|
|`/api/projects/{project_id}/documents/tag_counts`|GET|Get Document Tag Counts|Count the project's documents for each tag.|get_api_projects_project_id_documents_tag_counts.md|
|`/api/projects/{project_id}/documents/{document_id}`|GET|Get Document|Get one document's record: name, description, tags and file details.|get_api_projects_project_id_documents_document_id.md|
|`/api/projects/{project_id}/documents/{document_id}`|PATCH|Patch Document|Change a document's display name, description or tags.|patch_api_projects_project_id_documents_document_id.md|
|`/api/projects/{project_id}/documents/{document_id}`|DELETE|Delete Document|Delete one document, with its extractions.|delete_api_projects_project_id_documents_document_id.md|
|`/api/projects/{project_id}/documents/edit_tags`|POST|Edit Tags|Add tags to, or remove tags from, several documents at once.|post_api_projects_project_id_documents_edit_tags.md|
|`/api/projects/{project_id}/create_extractor_config`|POST|Create Extractor Config|Create an extractor config: how documents are turned into text (model, prompts, output format).|post_api_projects_project_id_create_extractor_config.md|
|`/api/projects/{project_id}/extractor_configs`|GET|Get Extractor Configs|List the project's extractor configs.|get_api_projects_project_id_extractor_configs.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}`|GET|Get Extractor Config|Get one extractor config.|get_api_projects_project_id_extractor_configs_extractor_config_id.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}`|PATCH|Patch Extractor Config|Change an extractor config's name or description, or archive it.|patch_api_projects_project_id_extractor_configs_extractor_config_id.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}/run_extractor_config`|GET|Run Extractor Config|Extract the text of the project's documents with one extractor config. Streams progress as events.|get_api_projects_project_id_extractor_configs_extractor_config_id_run_extractor_config.md|
|`/api/projects/{project_id}/documents/{document_id}/extractions`|GET|Get Extractions|List a document's extractions, one per extractor config that ran on it.|get_api_projects_project_id_documents_document_id_extractions.md|
|`/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}`|GET|Get Extraction|Get one extraction of a document, with its text.|get_api_projects_project_id_documents_document_id_extractions_extraction_id.md|
|`/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}`|DELETE|Delete Extraction|Delete one extraction of a document.|delete_api_projects_project_id_documents_document_id_extractions_extraction_id.md|
|`/api/projects/{project_id}/documents/{document_id}/download_extraction/{extraction_id}`|GET|Download Extraction|Download an extraction's text as a file.|get_api_projects_project_id_documents_document_id_download_extraction_extraction_id.md|
|`/api/projects/{project_id}/documents/delete`|POST|Delete Documents|Delete several documents, with their extractions.|post_api_projects_project_id_documents_delete.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}/progress`|GET|Get Extraction Progress|Get how many of the project's documents an extractor config has extracted.|get_api_projects_project_id_extractor_configs_extractor_config_id_progress.md|
|`/api/projects/{project_id}/documents/{document_id}/extract`|POST|Extract File|Extract one document's text with the given extractor configs, or all active ones. Streams progress.|post_api_projects_project_id_documents_document_id_extract.md|
|`/api/projects/{project_id}/create_chunker_config`|POST|Create Chunker Config|Create a chunker config: how extracted text is split into chunks for search.|post_api_projects_project_id_create_chunker_config.md|
|`/api/projects/{project_id}/chunker_configs`|GET|Get Chunker Configs|List the project's chunker configs.|get_api_projects_project_id_chunker_configs.md|
|`/api/projects/{project_id}/create_embedding_config`|POST|Create Embedding Config|Create an embedding config: the embedding model and settings for search chunks.|post_api_projects_project_id_create_embedding_config.md|
|`/api/projects/{project_id}/embedding_configs`|GET|Get Embedding Configs|List the project's embedding configs.|get_api_projects_project_id_embedding_configs.md|
|`/api/projects/{project_id}/create_reranker_config`|POST|Create Reranker Config|Create a reranker config: the model that reorders search results.|post_api_projects_project_id_create_reranker_config.md|
|`/api/projects/{project_id}/reranker_configs`|GET|Get Reranker Configs|List the project's reranker configs.|get_api_projects_project_id_reranker_configs.md|
|`/api/projects/{project_id}/embedding_configs/{embedding_config_id}`|GET|Get Embedding Config|Get one embedding config.|get_api_projects_project_id_embedding_configs_embedding_config_id.md|
|`/api/projects/{project_id}/create_vector_store_config`|POST|Create Vector Store Config|Create a vector store config: the index type and search settings for RAG.|post_api_projects_project_id_create_vector_store_config.md|
|`/api/projects/{project_id}/vector_store_configs`|GET|Get Vector Store Configs|List the project's vector store configs.|get_api_projects_project_id_vector_store_configs.md|
|`/api/projects/{project_id}/rag_configs/{rag_config_id}`|GET|Get Rag Config|Get one RAG config with its sub-configs.|get_api_projects_project_id_rag_configs_rag_config_id.md|
|`/api/projects/{project_id}/rag_configs/{rag_config_id}`|PATCH|Update Rag Config|Change a RAG config's name, description or archived flag.|patch_api_projects_project_id_rag_configs_rag_config_id.md|
|`/api/projects/{project_id}/rag_configs/create_rag_config`|POST|Create Rag Config|Create a RAG config from an extractor, chunker, embedding and vector store config. It becomes a sear...|post_api_projects_project_id_rag_configs_create_rag_config.md|
|`/api/projects/{project_id}/rag_configs`|GET|Get Rag Configs|List the project's RAG configs, each with its sub-configs.|get_api_projects_project_id_rag_configs.md|
|`/api/projects/{project_id}/rag_configs/{rag_config_id}/run`|GET|Run Rag Config|Build a RAG config's search index: extract, chunk, embed and index the documents. Streams progress.|get_api_projects_project_id_rag_configs_rag_config_id_run.md|
|`/api/projects/{project_id}/rag_configs/progress`|POST|Get Rag Config Progress|Get how far the index of each RAG config is built, for some or all of the project's RAG configs.|post_api_projects_project_id_rag_configs_progress.md|
|`/api/projects/{project_id}/rag_configs/{rag_config_id}/search`|POST|Search Rag Config|Search the vector store associated with a RAG config.|post_api_projects_project_id_rag_configs_rag_config_id_search.md|
|`/api/projects/{project_id}/check_library_state`|GET|Check Library State|Check whether the project's document library is empty.|get_api_projects_project_id_check_library_state.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}/documents/{document_id}/ephemeral_split`|POST|Ephemeral Split Document|Return chunks for a document extraction using FixedWindowChunker without persisting.  If chunk_size ...|post_api_projects_project_id_extractor_configs_extractor_config_id_documents_document_id_ephemeral_split.md|
