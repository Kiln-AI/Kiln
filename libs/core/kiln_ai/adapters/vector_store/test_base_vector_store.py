from unittest.mock import MagicMock

import pytest

from kiln_ai.adapters.vector_store.base_vector_store_adapter import (
    BaseVectorStoreAdapter,
    BaseVectorStoreCollection,
    SimilarityMetric,
)
from kiln_ai.datamodel.vector_store import VectorStoreConfig


class TestBaseVectorStoreAdapter:
    """Test the base vector store adapter abstract class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that the abstract base class cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseVectorStoreAdapter(MagicMock(spec=VectorStoreConfig))


class TestBaseVectorStoreCollection:
    """Test the base vector store collection abstract class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that the abstract base class cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseVectorStoreCollection(MagicMock(spec=VectorStoreConfig))


class TestSimilarityMetric:
    """Test the similarity metric enum."""

    def test_enum_values(self):
        """Test that the enum has the expected values."""
        assert SimilarityMetric.L2 == "l2"
        assert SimilarityMetric.COSINE == "cosine"
        assert SimilarityMetric.DOT_PRODUCT == "dot_product"
