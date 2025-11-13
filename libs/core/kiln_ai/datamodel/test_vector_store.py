import json

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.vector_store import VectorStoreConfig, VectorStoreType


@pytest.fixture
def mock_project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    return project


@pytest.fixture
def mock_vector_store_fts_config_properties():
    return {
        "similarity_top_k": 10,
        "overfetch_factor": 2,
        "vector_column_name": "vector",
        "text_key": "text",
        "doc_id_key": "doc_id",
        "store_type": VectorStoreType.LANCE_DB_FTS,
    }


@pytest.fixture
def mock_vector_store_vector_config_properties():
    return {
        "similarity_top_k": 10,
        "overfetch_factor": 2,
        "vector_column_name": "vector",
        "text_key": "text",
        "doc_id_key": "doc_id",
        "nprobes": 1,
        "store_type": VectorStoreType.LANCE_DB_VECTOR,
    }


@pytest.fixture
def mock_vector_store_hybrid_config_properties():
    return {
        "similarity_top_k": 10,
        "overfetch_factor": 2,
        "vector_column_name": "vector",
        "text_key": "text",
        "doc_id_key": "doc_id",
        "nprobes": 1,
        "store_type": VectorStoreType.LANCE_DB_HYBRID,
    }


class TestVectorStoreType:
    def test_vector_store_type_values(self):
        """Test that VectorStoreType enum has expected values."""
        assert VectorStoreType.LANCE_DB_FTS == "lancedb_fts"
        assert VectorStoreType.LANCE_DB_HYBRID == "lancedb_hybrid"
        assert VectorStoreType.LANCE_DB_VECTOR == "lancedb_vector"


class TestVectorStoreConfig:
    def test_invalid_store_type(self, mock_vector_store_fts_config_properties):
        """Test creating VectorStoreConfig with invalid store type."""
        with pytest.raises(ValidationError, match="Input should be"):
            VectorStoreConfig(
                name="test_store",
                store_type="invalid_type",  # type: ignore
                properties=mock_vector_store_fts_config_properties,
            )

    def test_invalid_store_type_after_creation(
        self, mock_vector_store_fts_config_properties
    ):
        """Test creating VectorStoreConfig with invalid store type after creation."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
        )
        with pytest.raises(ValidationError, match="Input should be"):
            config.store_type = "invalid_type"  # type: ignore

    def test_valid_lance_db_fts_vector_store_config(
        self, mock_vector_store_fts_config_properties
    ):
        """Test creating valid VectorStoreConfig with LanceDB FTS."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
        )

        assert config.name == "test_store"
        assert config.store_type == VectorStoreType.LANCE_DB_FTS
        assert config.properties["similarity_top_k"] == 10
        assert config.properties["overfetch_factor"] == 2
        assert config.properties["vector_column_name"] == "vector"
        assert config.properties["text_key"] == "text"
        assert config.properties["doc_id_key"] == "doc_id"

    def test_valid_lance_db_vector_store_config(
        self, mock_vector_store_vector_config_properties
    ):
        """Test creating valid VectorStoreConfig with LanceDB Vector."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_VECTOR,
            properties=mock_vector_store_vector_config_properties,
        )

        assert config.name == "test_store"
        assert config.store_type == VectorStoreType.LANCE_DB_VECTOR
        assert config.lancedb_vector_properties["similarity_top_k"] == 10
        assert config.lancedb_vector_properties["nprobes"] == 1

    def test_valid_lance_db_hybrid_store_config(
        self, mock_vector_store_hybrid_config_properties
    ):
        """Test creating valid VectorStoreConfig with LanceDB Hybrid."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_HYBRID,
            properties=mock_vector_store_hybrid_config_properties,
        )

        assert config.name == "test_store"
        assert config.store_type == VectorStoreType.LANCE_DB_HYBRID
        assert config.lancedb_hybrid_properties["nprobes"] == 1

    def test_vector_store_config_missing_required_property(
        self, mock_vector_store_fts_config_properties
    ):
        """Test VectorStoreConfig validation fails when required property is missing."""
        mock_vector_store_fts_config_properties.pop("similarity_top_k")
        with pytest.raises(
            ValidationError,
            match=r"1 validation error for VectorStoreConfig\nproperties\.lancedb_fts\.similarity_top_k",
        ):
            VectorStoreConfig(
                name="test_store",
                store_type=VectorStoreType.LANCE_DB_FTS,
                properties=mock_vector_store_fts_config_properties,
            )

    def test_vector_store_config_invalid_property_type(
        self, mock_vector_store_fts_config_properties
    ):
        """Test VectorStoreConfig validation fails when property has wrong type."""
        mock_vector_store_fts_config_properties["similarity_top_k"] = "not_an_int"
        with pytest.raises(
            ValidationError,
            match=r"1 validation error for VectorStoreConfig\nproperties\.lancedb_fts\.similarity_top_k",
        ):
            VectorStoreConfig(
                name="test_store",
                store_type=VectorStoreType.LANCE_DB_FTS,
                properties=mock_vector_store_fts_config_properties,
            )

    def test_vector_store_config_fts_missing_nprobes_is_valid(
        self, mock_vector_store_fts_config_properties
    ):
        """Test VectorStoreConfig with FTS type doesn't require nprobes."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
        )
        assert config.store_type == VectorStoreType.LANCE_DB_FTS

    def test_vector_store_config_vector_missing_nprobes_fails(
        self, mock_vector_store_vector_config_properties
    ):
        """Test VectorStoreConfig with VECTOR type requires nprobes."""
        mock_vector_store_vector_config_properties.pop("nprobes")
        with pytest.raises(
            ValidationError,
            match=r"1 validation error for VectorStoreConfig\nproperties\.lancedb_vector\.nprobes",
        ):
            VectorStoreConfig(
                name="test_store",
                store_type=VectorStoreType.LANCE_DB_VECTOR,
                properties=mock_vector_store_vector_config_properties,
            )

    def test_lancedb_vector_properties(
        self, mock_vector_store_vector_config_properties
    ):
        """Test lancedb_vector_properties method returns correct LanceDBConfigVectorProperties."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_VECTOR,
            properties=mock_vector_store_vector_config_properties,
        )

        props = config.lancedb_vector_properties

        assert props["similarity_top_k"] == 10
        assert props["overfetch_factor"] == 2
        assert props["vector_column_name"] == "vector"
        assert props["text_key"] == "text"
        assert props["doc_id_key"] == "doc_id"
        assert props["nprobes"] == 1

    def test_lancedb_hybrid_properties(
        self, mock_vector_store_hybrid_config_properties
    ):
        """Test lancedb_hybrid_properties method returns correct LanceDBConfigHybridProperties."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_HYBRID,
            properties=mock_vector_store_hybrid_config_properties,
        )

        props = config.lancedb_hybrid_properties

        assert props["similarity_top_k"] == 10
        assert props["overfetch_factor"] == 2
        assert props["vector_column_name"] == "vector"
        assert props["text_key"] == "text"
        assert props["doc_id_key"] == "doc_id"
        assert props["nprobes"] == 1

    def test_lancedb_fts_properties(self, mock_vector_store_fts_config_properties):
        """Test lancedb_fts_properties method returns correct LanceDBConfigFTSProperties."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
        )

        props = config.lancedb_fts_properties

        assert props["similarity_top_k"] == 10
        assert props["overfetch_factor"] == 2
        assert props["vector_column_name"] == "vector"
        assert props["text_key"] == "text"
        assert props["doc_id_key"] == "doc_id"
        assert "nprobes" not in props

    def test_lancedb_properties_throws_on_mismatching_store_type(
        self,
        mock_vector_store_vector_config_properties,
        mock_vector_store_fts_config_properties,
        mock_vector_store_hybrid_config_properties,
    ):
        """Test lancedb_properties method raises ValueError for mismatching store type."""
        config1 = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
        )
        with pytest.raises(ValueError):
            config1.lancedb_vector_properties
        with pytest.raises(ValueError):
            config1.lancedb_hybrid_properties

        config2 = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_VECTOR,
            properties=mock_vector_store_vector_config_properties,
        )
        with pytest.raises(ValueError):
            config2.lancedb_fts_properties
        with pytest.raises(ValueError):
            config2.lancedb_hybrid_properties

        config3 = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_HYBRID,
            properties=mock_vector_store_hybrid_config_properties,
        )
        with pytest.raises(ValueError):
            config3.lancedb_fts_properties
        with pytest.raises(ValueError):
            config3.lancedb_vector_properties

    def test_vector_store_config_inherits_from_kiln_parented_model(
        self, mock_vector_store_fts_config_properties
    ):
        """Test that VectorStoreConfig inherits from KilnParentedModel."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
        )

        # Check that it has the expected base fields
        assert hasattr(config, "id")
        assert hasattr(config, "v")
        assert hasattr(config, "created_at")
        assert hasattr(config, "created_by")
        assert hasattr(config, "parent")

    @pytest.mark.parametrize(
        "name",
        ["valid_name", "valid name", "valid-name", "valid_name_123", "VALID_NAME"],
    )
    def test_vector_store_config_valid_names(
        self, name, mock_vector_store_fts_config_properties
    ):
        """Test VectorStoreConfig accepts valid names."""
        config = VectorStoreConfig(
            name=name,
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
        )
        assert config.name == name

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "a" * 121,  # Too long
        ],
    )
    def test_vector_store_config_invalid_names(
        self, name, mock_vector_store_fts_config_properties
    ):
        """Test VectorStoreConfig rejects invalid names."""
        with pytest.raises(ValidationError):
            VectorStoreConfig(
                name=name,
                store_type=VectorStoreType.LANCE_DB_FTS,
                properties=mock_vector_store_fts_config_properties,
            )

    def test_parent_project(
        self, mock_project, mock_vector_store_fts_config_properties
    ):
        """Test that parent project is returned correctly."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
            parent=mock_project,
        )

        assert config.parent_project() is mock_project

    def test_vector_store_config_parent_project_none(
        self, mock_vector_store_fts_config_properties
    ):
        """Test that parent project is None if not set."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
        )

        assert config.parent_project() is None

    def test_project_has_vector_store_configs(
        self, mock_project, mock_vector_store_fts_config_properties
    ):
        """Test that project has vector store configs."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB_FTS,
            properties=mock_vector_store_fts_config_properties,
            parent=mock_project,
        )
        config.save_to_file()

        assert len(mock_project.vector_store_configs(readonly=True)) == 1
        assert config.id in [
            vc.id for vc in mock_project.vector_store_configs(readonly=True)
        ]


class TestBackwardCompatibility:
    def test_backward_compatibility_with_missing_store_type_fts(self, tmp_path):
        """
        We added discriminated union and the store_type in the properties, but older
        configs did not have the store_type in the properties. This test ensures that
        we can load these old configs and that the store_type is added to the properties.
        """
        # we write the config to a file, and then we try to load it from file
        file_path = tmp_path / "test_store.kiln"
        config_serialized = {
            "v": 1,
            "id": "310815630212",
            "created_at": "2025-10-15T01:16:38.380098",
            "created_by": "leonardmarcq",
            "name": "Full-Text Search",
            "description": None,
            "store_type": VectorStoreType.LANCE_DB_FTS,
            "properties": {
                "overfetch_factor": 1,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
                "similarity_top_k": 10,
            },
            "model_type": "vector_store_config",
        }
        with open(file_path, "w") as f:
            json.dump(config_serialized, f, ensure_ascii=False, indent=4)
        config = VectorStoreConfig.load_from_file(file_path)

        # when loading from file, the store_type is added to the properties
        assert config.store_type == VectorStoreType.LANCE_DB_FTS
        assert config.properties["similarity_top_k"] == 10
        assert config.properties["overfetch_factor"] == 1
        assert config.properties["vector_column_name"] == "vector"
        assert config.properties["text_key"] == "text"
        assert config.properties["doc_id_key"] == "doc_id"

        # this should be added automatically by the loader
        assert config.properties["store_type"] == VectorStoreType.LANCE_DB_FTS

        # save the file and check that store_type makes it into the properties
        config.save_to_file()
        config_restored = VectorStoreConfig.load_from_file(file_path)
        assert config_restored.store_type == VectorStoreType.LANCE_DB_FTS
        assert config_restored.properties["store_type"] == VectorStoreType.LANCE_DB_FTS

    def test_backward_compatibility_with_missing_store_type_vector(self, tmp_path):
        """
        We added discriminated union and the store_type in the properties, but older
        configs did not have the store_type in the properties. This test ensures that
        we can load these old configs and that the store_type is added to the properties.
        """
        # we write the config to a file, and then we try to load it from file
        file_path = tmp_path / "test_store.kiln"
        config_serialized = {
            "v": 1,
            "id": "310815630212",
            "created_at": "2025-10-15T01:16:38.380098",
            "created_by": "leonardmarcq",
            "name": "Vector Search",
            "description": None,
            "store_type": VectorStoreType.LANCE_DB_VECTOR,
            "properties": {
                "overfetch_factor": 1,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
                "similarity_top_k": 10,
                "nprobes": 20,
            },
            "model_type": "vector_store_config",
        }
        with open(file_path, "w") as f:
            json.dump(config_serialized, f, ensure_ascii=False, indent=4)
        config = VectorStoreConfig.load_from_file(file_path)

        # when loading from file, the store_type is added to the properties
        assert config.store_type == VectorStoreType.LANCE_DB_VECTOR
        assert config.properties["similarity_top_k"] == 10
        assert config.properties["overfetch_factor"] == 1
        assert config.properties["vector_column_name"] == "vector"
        assert config.properties["text_key"] == "text"
        assert config.properties["doc_id_key"] == "doc_id"

        # this should be added automatically by the loader
        assert config.properties["store_type"] == VectorStoreType.LANCE_DB_VECTOR

        # save the file and check that store_type makes it into the properties
        config.save_to_file()
        config_restored = VectorStoreConfig.load_from_file(file_path)
        assert config_restored.store_type == VectorStoreType.LANCE_DB_VECTOR
        assert (
            config_restored.properties["store_type"] == VectorStoreType.LANCE_DB_VECTOR
        )

    def test_backward_compatibility_with_missing_store_type_hybrid(self, tmp_path):
        """
        We added discriminated union and the store_type in the properties, but older
        configs did not have the store_type in the properties. This test ensures that
        we can load these old configs and that the store_type is added to the properties.
        """
        # we write the config to a file, and then we try to load it from file
        file_path = tmp_path / "test_store.kiln"
        config_serialized = {
            "v": 1,
            "id": "310815630212",
            "created_at": "2025-10-15T01:16:38.380098",
            "created_by": "leonardmarcq",
            "name": "Hybrid Search - Vector and Full-Text",
            "description": None,
            "store_type": VectorStoreType.LANCE_DB_HYBRID,
            "properties": {
                "overfetch_factor": 1,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
                "similarity_top_k": 10,
                "nprobes": 20,
            },
            "model_type": "vector_store_config",
        }
        with open(file_path, "w") as f:
            json.dump(config_serialized, f, ensure_ascii=False, indent=4)
        config = VectorStoreConfig.load_from_file(file_path)

        # when loading from file, the store_type is added to the properties
        assert config.store_type == VectorStoreType.LANCE_DB_HYBRID
        assert config.properties["similarity_top_k"] == 10
        assert config.properties["overfetch_factor"] == 1
        assert config.properties["vector_column_name"] == "vector"
        assert config.properties["text_key"] == "text"
        assert config.properties["doc_id_key"] == "doc_id"

        # this should be added automatically by the loader
        assert config.properties["store_type"] == VectorStoreType.LANCE_DB_HYBRID

        # save the file and check that store_type makes it into the properties
        config.save_to_file()
        config_restored = VectorStoreConfig.load_from_file(file_path)
        assert config_restored.store_type == VectorStoreType.LANCE_DB_HYBRID
        assert (
            config_restored.properties["store_type"] == VectorStoreType.LANCE_DB_HYBRID
        )

    def test_backward_compatibility_fts_nprobes_extra(self, tmp_path):
        # should not crash because nprobes is in properties even if it is not required
        file_path = tmp_path / "test_store.kiln"
        config_serialized = {
            "v": 1,
            "id": "310815630212",
            "created_at": "2025-10-15T01:16:38.380098",
            "created_by": "leonardmarcq",
            "name": "FTS Search",
            "description": None,
            "store_type": VectorStoreType.LANCE_DB_FTS,
            "properties": {
                "overfetch_factor": 1,
                "vector_column_name": "vector",
                "text_key": "text",
                "doc_id_key": "doc_id",
                "similarity_top_k": 10,
                "nprobes": 20,
            },
            "model_type": "vector_store_config",
        }
        with open(file_path, "w") as f:
            json.dump(config_serialized, f, ensure_ascii=False, indent=4)
        config = VectorStoreConfig.load_from_file(file_path)

        # save the file and check that extra properties are not persisted
        config.save_to_file()
        config_restored = VectorStoreConfig.load_from_file(file_path)
        assert "nprobes" not in config_restored.properties
