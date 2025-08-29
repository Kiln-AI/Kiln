import pytest

from kiln_ai.adapters.embedding.base_embedding_adapter import (
    BaseEmbeddingAdapter,
    Embedding,
    EmbeddingResult,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.embedding import EmbeddingConfig


class MockEmbeddingAdapter(BaseEmbeddingAdapter):
    """Concrete implementation of BaseEmbeddingAdapter for testing purposes."""

    async def _generate_embeddings(self, text_inputs: list[str]) -> EmbeddingResult:
        # Simple test implementation that returns mock embeddings
        embeddings = []
        for i, _ in enumerate(text_inputs):
            embeddings.append(Embedding(vector=[0.1 * (i + 1)] * 3))

        return EmbeddingResult(embeddings=embeddings)


class MockEmbeddingAdapterWithUsage(BaseEmbeddingAdapter):
    """Concrete implementation that includes usage information."""

    async def _generate_embeddings(self, text_inputs: list[str]) -> EmbeddingResult:
        from litellm import Usage

        embeddings = []
        for i, _ in enumerate(text_inputs):
            embeddings.append(Embedding(vector=[0.1 * (i + 1)] * 3))

        usage = Usage(
            prompt_tokens=len(text_inputs) * 10, total_tokens=len(text_inputs) * 10
        )
        return EmbeddingResult(embeddings=embeddings, usage=usage)


@pytest.fixture
def mock_embedding_config():
    """Create a mock embedding config for testing."""
    return EmbeddingConfig(
        name="test-embedding",
        model_provider_name=ModelProviderName.openai,
        model_name="openai_text_embedding_3_small",
        properties={},
    )


@pytest.fixture
def test_adapter(mock_embedding_config):
    """Create a test adapter instance."""
    return MockEmbeddingAdapter(mock_embedding_config)


@pytest.fixture
def test_adapter_with_usage(mock_embedding_config):
    """Create a test adapter instance that includes usage information."""
    return MockEmbeddingAdapterWithUsage(mock_embedding_config)


class TestEmbedding:
    """Test the Embedding model."""

    def test_creation(self):
        """Test creating a Embedding with a vector."""
        vector = [0.1, 0.2, 0.3]
        embedding = Embedding(vector=vector)
        assert embedding.vector == vector

    def test_empty_vector(self):
        """Test creating a Embedding with an empty vector."""
        embedding = Embedding(vector=[])
        assert embedding.vector == []

    def test_large_vector(self):
        """Test creating a Embedding with a large vector."""
        vector = [0.1] * 1536
        embedding = Embedding(vector=vector)
        assert len(embedding.vector) == 1536
        assert all(v == 0.1 for v in embedding.vector)


class TestEmbeddingResult:
    """Test the EmbeddingResult model."""

    def test_creation_with_embeddings(self):
        """Test creating an EmbeddingResult with embeddings."""
        embeddings = [
            Embedding(vector=[0.1, 0.2, 0.3]),
            Embedding(vector=[0.4, 0.5, 0.6]),
        ]
        result = EmbeddingResult(embeddings=embeddings)
        assert result.embeddings == embeddings
        assert result.usage is None

    def test_creation_with_usage(self):
        """Test creating an EmbeddingResult with usage information."""
        from litellm import Usage

        embeddings = [Embedding(vector=[0.1, 0.2, 0.3])]
        usage = Usage(prompt_tokens=10, total_tokens=10)
        result = EmbeddingResult(embeddings=embeddings, usage=usage)
        assert result.embeddings == embeddings
        assert result.usage == usage

    def test_empty_embeddings(self):
        """Test creating an EmbeddingResult with empty embeddings."""
        result = EmbeddingResult(embeddings=[])
        assert result.embeddings == []
        assert result.usage is None


class TestBaseEmbeddingAdapter:
    """Test the BaseEmbeddingAdapter abstract base class."""

    def test_init(self, mock_embedding_config):
        """Test successful initialization of the adapter."""
        adapter = MockEmbeddingAdapter(mock_embedding_config)
        assert adapter.embedding_config == mock_embedding_config
        assert adapter.embedding_config.name == "test-embedding"
        assert adapter.embedding_config.model_provider_name == ModelProviderName.openai
        assert adapter.embedding_config.model_name == "openai_text_embedding_3_small"
        assert adapter.embedding_config.properties == {}

    def test_cannot_instantiate_abstract_class(self, mock_embedding_config):
        """Test that BaseEmbeddingAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseEmbeddingAdapter(mock_embedding_config)

    async def test_generate_embeddings_empty_list(self, test_adapter):
        """Test embed method with empty text list."""
        result = await test_adapter.generate_embeddings([])
        assert result.embeddings == []
        assert result.usage is None

    async def test_generate_embeddings_single_text(self, test_adapter):
        """Test embed method with a single text."""
        result = await test_adapter.generate_embeddings(["hello world"])
        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == [0.1, 0.1, 0.1]
        assert result.usage is None

    async def test_generate_embeddings_multiple_texts(self, test_adapter):
        """Test embed method with multiple texts."""
        texts = ["hello world", "my name is john", "i like to eat apples"]
        result = await test_adapter.generate_embeddings(texts)
        assert len(result.embeddings) == 3
        assert result.embeddings[0].vector == [0.1, 0.1, 0.1]
        assert result.embeddings[1].vector == [0.2, 0.2, 0.2]
        assert result.embeddings[2].vector == pytest.approx([0.3, 0.3, 0.3])
        assert result.usage is None

    async def test_generate_embeddings_with_usage(self, test_adapter_with_usage):
        """Test embed method with usage information."""
        texts = ["hello", "world"]
        result = await test_adapter_with_usage.generate_embeddings(texts)
        assert len(result.embeddings) == 2
        assert result.embeddings[0].vector == [0.1, 0.1, 0.1]
        assert result.embeddings[1].vector == [0.2, 0.2, 0.2]
        assert result.usage is not None
        assert result.usage.prompt_tokens == 20
        assert result.usage.total_tokens == 20

    async def test_generate_embeddings_with_none_input(self, test_adapter):
        """Test embed method with None input (should be treated as empty list)."""
        result = await test_adapter.generate_embeddings(None)  # type: ignore
        assert result.embeddings == []
        assert result.usage is None

    async def test_generate_embeddings_with_whitespace_only_texts(self, test_adapter):
        """Test embed method with texts containing only whitespace."""
        texts = ["   ", "\n", "\t"]
        result = await test_adapter.generate_embeddings(texts)
        assert len(result.embeddings) == 3
        # Should still generate embeddings for whitespace-only texts
        assert result.embeddings[0].vector == [0.1, 0.1, 0.1]
        assert result.embeddings[1].vector == [0.2, 0.2, 0.2]
        assert result.embeddings[2].vector == pytest.approx([0.3, 0.3, 0.3])

    async def test_generate_embeddings_with_duplicate_texts(self, test_adapter):
        """Test embed method with duplicate texts."""
        texts = ["hello", "hello", "world"]
        result = await test_adapter.generate_embeddings(texts)
        assert len(result.embeddings) == 3
        # Each text should get its own embedding, even if duplicate
        assert result.embeddings[0].vector == [0.1, 0.1, 0.1]
        assert result.embeddings[1].vector == [0.2, 0.2, 0.2]
        assert result.embeddings[2].vector == pytest.approx([0.3, 0.3, 0.3])


class TestBaseEmbeddingAdapterEdgeCases:
    """Test edge cases for BaseEmbeddingAdapter."""

    async def test_generate_embeddings_with_very_long_text(self, test_adapter):
        """Test embed method with very long text."""
        long_text = "a" * 10000
        result = await test_adapter.generate_embeddings([long_text])
        assert len(result.embeddings) == 1
        assert result.embeddings[0].vector == [0.1, 0.1, 0.1]

    async def test_generate_embeddings_with_special_characters(self, test_adapter):
        """Test embed method with special characters."""
        texts = ["hello\nworld", "test\twith\ttabs", "unicode: 🚀🌟"]
        result = await test_adapter.generate_embeddings(texts)
        assert len(result.embeddings) == 3
        assert result.embeddings[0].vector == [0.1, 0.1, 0.1]
        assert result.embeddings[1].vector == [0.2, 0.2, 0.2]
        assert result.embeddings[2].vector == pytest.approx([0.3, 0.3, 0.3])

    async def test_generate_embeddings_with_empty_strings(self, test_adapter):
        """Test embed method with empty strings."""
        texts = ["", "", ""]
        result = await test_adapter.generate_embeddings(texts)
        assert len(result.embeddings) == 3
        assert result.embeddings[0].vector == [0.1, 0.1, 0.1]
        assert result.embeddings[1].vector == [0.2, 0.2, 0.2]
        assert result.embeddings[2].vector == pytest.approx([0.3, 0.3, 0.3])

    def test_embedding_config_properties(self, mock_embedding_config):
        """Test that embedding config properties are accessible."""
        mock_embedding_config.properties = {"dimensions": 1536, "normalize": True}
        adapter = MockEmbeddingAdapter(mock_embedding_config)
        assert adapter.embedding_config.properties["dimensions"] == 1536
        assert adapter.embedding_config.properties["normalize"] is True


class TestBaseEmbeddingAdapterIntegration:
    """Integration tests for BaseEmbeddingAdapter."""

    async def test_generate_embeddings_method_calls_abstract_method(
        self, mock_embedding_config
    ):
        """Test that embed method properly calls the abstract _embed method."""

        # Create a mock adapter that tracks if _embed was called
        class MockAdapter(BaseEmbeddingAdapter):
            def __init__(self, config):
                super().__init__(config)
                self._generate_embeddings_called = False
                self._generate_embeddings_args = None

            async def _generate_embeddings(
                self, text_inputs: list[str]
            ) -> EmbeddingResult:
                self._generate_embeddings_called = True
                self._generate_embeddings_args = text_inputs
                return EmbeddingResult(embeddings=[])

        adapter = MockAdapter(mock_embedding_config)
        texts = ["hello", "world"]

        result = await adapter.generate_embeddings(texts)

        assert adapter._generate_embeddings_called
        assert adapter._generate_embeddings_args == texts
        assert result.embeddings == []
        assert result.usage is None

    async def test_generate_embeddings_empty_list_does_not_call_abstract_method(
        self, mock_embedding_config
    ):
        """Test that embed method with empty list does not call _embed."""

        class MockAdapter(BaseEmbeddingAdapter):
            def __init__(self, config):
                super().__init__(config)
                self._generate_embeddings_called = False

            async def _generate_embeddings(
                self, text_inputs: list[str]
            ) -> EmbeddingResult:
                self._generate_embeddings_called = True
                return EmbeddingResult(embeddings=[])

        adapter = MockAdapter(mock_embedding_config)

        result = await adapter.generate_embeddings([])

        assert not adapter._generate_embeddings_called
        assert result.embeddings == []
        assert result.usage is None
