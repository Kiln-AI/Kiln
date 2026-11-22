# Documents API

Manage documents, extraction, chunking, embedding, vector stores, and RAG configurations.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/documents/bulk`|POST|Bulk Create Documents||post_api_projects_project_id_documents_bulk.md|
|`/api/projects/{project_id}/documents`|GET|List Documents||get_api_projects_project_id_documents.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}/extractions`|GET|List Extractions for Extractor Config|Return mapping of document id to list of extractions for the given extractor config id.|get_api_projects_project_id_extractor_configs_extractor_config_id_extractions.md|
|`/api/projects/{project_id}/documents/tags`|GET|List Document Tags||get_api_projects_project_id_documents_tags.md|
|`/api/projects/{project_id}/documents/tag_counts`|GET|Get Document Tag Counts||get_api_projects_project_id_documents_tag_counts.md|
|`/api/projects/{project_id}/documents/{document_id}`|GET|Get Document||get_api_projects_project_id_documents_document_id.md|
|`/api/projects/{project_id}/documents/{document_id}`|PATCH|Patch Document||patch_api_projects_project_id_documents_document_id.md|
|`/api/projects/{project_id}/documents/{document_id}`|DELETE|Delete Document||delete_api_projects_project_id_documents_document_id.md|
|`/api/projects/{project_id}/documents/edit_tags`|POST|Edit Tags||post_api_projects_project_id_documents_edit_tags.md|
|`/api/projects/{project_id}/create_extractor_config`|POST|Create Extractor Config||post_api_projects_project_id_create_extractor_config.md|
|`/api/projects/{project_id}/extractor_configs`|GET|Get Extractor Configs||get_api_projects_project_id_extractor_configs.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}`|GET|Get Extractor Config||get_api_projects_project_id_extractor_configs_extractor_config_id.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}`|PATCH|Patch Extractor Config||patch_api_projects_project_id_extractor_configs_extractor_config_id.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}/run_extractor_config`|GET|Run Extractor Config||get_api_projects_project_id_extractor_configs_extractor_config_id_run_extractor_config.md|
|`/api/projects/{project_id}/documents/{document_id}/extractions`|GET|Get Extractions||get_api_projects_project_id_documents_document_id_extractions.md|
|`/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}`|GET|Get Extraction||get_api_projects_project_id_documents_document_id_extractions_extraction_id.md|
|`/api/projects/{project_id}/documents/{document_id}/extractions/{extraction_id}`|DELETE|Delete Extraction||delete_api_projects_project_id_documents_document_id_extractions_extraction_id.md|
|`/api/projects/{project_id}/documents/{document_id}/download_extraction/{extraction_id}`|GET|Download Extraction||get_api_projects_project_id_documents_document_id_download_extraction_extraction_id.md|
|`/api/projects/{project_id}/documents/delete`|POST|Delete Documents||post_api_projects_project_id_documents_delete.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}/progress`|GET|Get Extraction Progress||get_api_projects_project_id_extractor_configs_extractor_config_id_progress.md|
|`/api/projects/{project_id}/documents/{document_id}/extract`|POST|Extract File||post_api_projects_project_id_documents_document_id_extract.md|
|`/api/projects/{project_id}/create_chunker_config`|POST|Create Chunker Config||post_api_projects_project_id_create_chunker_config.md|
|`/api/projects/{project_id}/chunker_configs`|GET|Get Chunker Configs||get_api_projects_project_id_chunker_configs.md|
|`/api/projects/{project_id}/create_embedding_config`|POST|Create Embedding Config||post_api_projects_project_id_create_embedding_config.md|
|`/api/projects/{project_id}/embedding_configs`|GET|Get Embedding Configs||get_api_projects_project_id_embedding_configs.md|
|`/api/projects/{project_id}/create_reranker_config`|POST|Create Reranker Config||post_api_projects_project_id_create_reranker_config.md|
|`/api/projects/{project_id}/reranker_configs`|GET|Get Reranker Configs||get_api_projects_project_id_reranker_configs.md|
|`/api/projects/{project_id}/embedding_configs/{embedding_config_id}`|GET|Get Embedding Config||get_api_projects_project_id_embedding_configs_embedding_config_id.md|
|`/api/projects/{project_id}/create_vector_store_config`|POST|Create Vector Store Config||post_api_projects_project_id_create_vector_store_config.md|
|`/api/projects/{project_id}/vector_store_configs`|GET|Get Vector Store Configs||get_api_projects_project_id_vector_store_configs.md|
|`/api/projects/{project_id}/rag_configs/{rag_config_id}`|GET|Get Rag Config||get_api_projects_project_id_rag_configs_rag_config_id.md|
|`/api/projects/{project_id}/rag_configs/{rag_config_id}`|PATCH|Update Rag Config||patch_api_projects_project_id_rag_configs_rag_config_id.md|
|`/api/projects/{project_id}/rag_configs/create_rag_config`|POST|Create Rag Config||post_api_projects_project_id_rag_configs_create_rag_config.md|
|`/api/projects/{project_id}/rag_configs`|GET|Get Rag Configs||get_api_projects_project_id_rag_configs.md|
|`/api/projects/{project_id}/rag_configs/{rag_config_id}/run`|GET|Run Rag Config||get_api_projects_project_id_rag_configs_rag_config_id_run.md|
|`/api/projects/{project_id}/rag_configs/progress`|POST|Get Rag Config Progress||post_api_projects_project_id_rag_configs_progress.md|
|`/api/projects/{project_id}/rag_configs/{rag_config_id}/search`|POST|Search Rag Config|Search the vector store associated with a RAG config.|post_api_projects_project_id_rag_configs_rag_config_id_search.md|
|`/api/projects/{project_id}/check_library_state`|GET|Check Library State||get_api_projects_project_id_check_library_state.md|
|`/api/projects/{project_id}/extractor_configs/{extractor_config_id}/documents/{document_id}/ephemeral_split`|POST|Ephemeral Split Document|Return chunks for a document extraction using FixedWindowChunker without persisting.  If chunk_size ...|post_api_projects_project_id_extractor_configs_extractor_config_id_documents_document_id_ephemeral_split.md|
