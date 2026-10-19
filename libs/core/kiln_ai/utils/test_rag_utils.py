import pytest

from kiln_ai.adapters.rerankers.base_reranker import RerankDocument
from kiln_ai.adapters.vector_store.base_vector_store_adapter import SearchResult
from kiln_ai.utils.rag_utils import (
    convert_search_results_to_rerank_input,
    global_chunk_id,
    split_global_chunk_id,
)


class TestGlobalChunkId:
    def test_basic_id_format(self):
        result = global_chunk_id("doc123", 5)
        assert result == "doc123::5"

    def test_with_special_characters_in_document_id(self):
        result = global_chunk_id("doc-abc_123", 0)
        assert result == "doc-abc_123::0"

    def test_with_zero_chunk_idx(self):
        result = global_chunk_id("doc1", 0)
        assert result == "doc1::0"

    def test_with_large_chunk_idx(self):
        result = global_chunk_id("doc1", 9999)
        assert result == "doc1::9999"


class TestSplitGlobalChunkId:
    def test_basic_split(self):
        document_id, chunk_idx = split_global_chunk_id("doc123::5")
        assert document_id == "doc123"
        assert chunk_idx == 5
        assert isinstance(chunk_idx, int)

    def test_split_with_zero_chunk_idx(self):
        document_id, chunk_idx = split_global_chunk_id("doc1::0")
        assert document_id == "doc1"
        assert chunk_idx == 0

    def test_split_with_special_characters(self):
        document_id, chunk_idx = split_global_chunk_id("doc-abc_123::42")
        assert document_id == "doc-abc_123"
        assert chunk_idx == 42

    def test_split_with_large_chunk_idx(self):
        document_id, chunk_idx = split_global_chunk_id("doc1::9999")
        assert document_id == "doc1"
        assert chunk_idx == 9999

    def test_round_trip_conversion(self):
        original_doc_id = "test_doc_456"
        original_chunk_idx = 123
        global_id = global_chunk_id(original_doc_id, original_chunk_idx)
        doc_id, chunk_idx = split_global_chunk_id(global_id)
        assert doc_id == original_doc_id
        assert chunk_idx == original_chunk_idx

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "invalid_format",
            "",
            "doc::with::colons::0",
            "doc::with::colons",
        ],
    )
    def test_split_wrong_separator_count_raises_error(self, invalid_id):
        with pytest.raises(ValueError, match="Expected exactly one '::' separator"):
            split_global_chunk_id(invalid_id)

    @pytest.mark.parametrize(
        "invalid_chunk_idx",
        ["not_a_number", "", "1.5", "0x5"],
    )
    def test_split_non_integer_chunk_idx_raises_error(self, invalid_chunk_idx):
        with pytest.raises(ValueError, match="is not an integer"):
            split_global_chunk_id(f"doc123::{invalid_chunk_idx}")

    def test_split_error_message_includes_offending_id(self):
        with pytest.raises(ValueError) as exc_info:
            split_global_chunk_id("doc::with::colons::0")
        assert "doc::with::colons::0" in str(exc_info.value)


class TestConvertSearchResultsToRerankInput:
    def test_empty_list(self):
        result = convert_search_results_to_rerank_input([])
        assert result == []

    def test_single_search_result(self):
        search_results = [
            SearchResult(
                document_id="doc1",
                chunk_idx=0,
                chunk_text="This is some text",
                similarity=0.95,
            )
        ]
        result = convert_search_results_to_rerank_input(search_results)
        assert len(result) == 1
        assert isinstance(result[0], RerankDocument)
        assert result[0].id == "doc1::0"
        assert result[0].text == "This is some text"

    def test_multiple_search_results(self):
        search_results = [
            SearchResult(
                document_id="doc1",
                chunk_idx=0,
                chunk_text="First chunk",
                similarity=0.95,
            ),
            SearchResult(
                document_id="doc1",
                chunk_idx=1,
                chunk_text="Second chunk",
                similarity=0.85,
            ),
            SearchResult(
                document_id="doc2",
                chunk_idx=5,
                chunk_text="Another document chunk",
                similarity=0.75,
            ),
        ]
        result = convert_search_results_to_rerank_input(search_results)
        assert len(result) == 3
        assert result[0].id == "doc1::0"
        assert result[0].text == "First chunk"
        assert result[1].id == "doc1::1"
        assert result[1].text == "Second chunk"
        assert result[2].id == "doc2::5"
        assert result[2].text == "Another document chunk"

    def test_preserves_order(self):
        search_results = [
            SearchResult(
                document_id="doc3", chunk_idx=10, chunk_text="Third", similarity=0.5
            ),
            SearchResult(
                document_id="doc1", chunk_idx=0, chunk_text="First", similarity=0.9
            ),
            SearchResult(
                document_id="doc2", chunk_idx=5, chunk_text="Second", similarity=0.7
            ),
        ]
        result = convert_search_results_to_rerank_input(search_results)
        assert result[0].id == "doc3::10"
        assert result[1].id == "doc1::0"
        assert result[2].id == "doc2::5"

    def test_similarity_not_included_in_output(self):
        search_results = [
            SearchResult(
                document_id="doc1",
                chunk_idx=0,
                chunk_text="Some text",
                similarity=0.95,
            )
        ]
        result = convert_search_results_to_rerank_input(search_results)
        assert not hasattr(result[0], "similarity")
        assert result[0].model_fields_set == {"id", "text"}

    def test_with_none_similarity(self):
        search_results = [
            SearchResult(
                document_id="doc1", chunk_idx=0, chunk_text="Some text", similarity=None
            )
        ]
        result = convert_search_results_to_rerank_input(search_results)
        assert len(result) == 1
        assert result[0].id == "doc1::0"
        assert result[0].text == "Some text"
