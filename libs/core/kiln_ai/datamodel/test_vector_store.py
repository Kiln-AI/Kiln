import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.vector_store import (
    LanceDBConfigProperties,
    LanceDBTableSchemaVersion,
    LanceDBVectorIndexType,
    VectorStoreConfig,
    VectorStoreType,
)


class TestVectorStoreType:
    def test_vector_store_type_values(self):
        """Test that VectorStoreType enum has expected values."""
        assert VectorStoreType.LANCE_DB == "lancedb"


class TestLanceDBTableSchemaVersion:
    def test_lance_db_table_schema_version_values(self):
        """Test that LanceDBTableSchemaVersion enum has expected values."""
        assert LanceDBTableSchemaVersion.V1 == "1"


class TestLanceDBConfigProperties:
    def test_valid_lance_db_config_properties(self):
        """Test creating valid LanceDBConfigProperties."""
        config = LanceDBConfigProperties(
            table_schema_version=LanceDBTableSchemaVersion.V1,
            vector_index_type=LanceDBVectorIndexType.BRUTEFORCE,
        )

        assert config.table_schema_version == LanceDBTableSchemaVersion.V1
        assert config.vector_index_type == LanceDBVectorIndexType.BRUTEFORCE

    def test_lance_db_config_properties_with_string_schema_version(self):
        """Test creating LanceDBConfigProperties with string schema version."""
        config = LanceDBConfigProperties(
            table_schema_version="1",
            vector_index_type=LanceDBVectorIndexType.BRUTEFORCE,
        )

        assert config.table_schema_version == LanceDBTableSchemaVersion.V1


class TestVectorStoreConfig:
    def test_valid_lance_db_vector_store_config(self):
        """Test creating valid VectorStoreConfig with LanceDB."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB,
            properties={
                "table_schema_version": "1",
                "vector_index_type": "bruteforce",
            },
        )

        assert config.name == "test_store"
        assert config.store_type == VectorStoreType.LANCE_DB
        assert config.properties["table_schema_version"] == "1"
        assert config.properties["vector_index_type"] == "bruteforce"

    def test_vector_store_config_missing_table_schema_version(self):
        """Test VectorStoreConfig validation fails when table_schema_version is missing."""
        with pytest.raises(
            ValidationError,
            match="LanceDB table schema version not found in properties",
        ):
            VectorStoreConfig(
                name="test_store",
                store_type=VectorStoreType.LANCE_DB,
                properties={
                    "vector_index_type": "bruteforce",
                },
            )

    def test_vector_store_config_invalid_table_schema_version(self):
        """Test VectorStoreConfig validation fails when table_schema_version is invalid."""
        with pytest.raises(
            ValidationError,
            match="LanceDB table schema version not found in properties",
        ):
            VectorStoreConfig(
                name="test_store",
                store_type=VectorStoreType.LANCE_DB,
                properties={
                    "path": "/path/to/db",
                    "table_schema_version": "invalid",
                    "vector_index_type": "bruteforce",
                },
            )

    def test_vector_store_config_invalid_store_type(self):
        """Test VectorStoreConfig validation fails with invalid store type."""
        with pytest.raises(ValidationError, match="Input should be 'lancedb'"):
            VectorStoreConfig(
                name="test_store",
                store_type="invalid_type",
                properties={
                    "path": "/path/to/db",
                    "table_schema_version": "1",
                    "vector_index_type": "bruteforce",
                },
            )

    def test_lancedb_typed_properties(self):
        """Test lancedb_typed_properties method returns correct LanceDBConfigProperties."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB,
            properties={
                "table_schema_version": "1",
                "vector_index_type": "bruteforce",
            },
        )

        typed_props = config.lancedb_typed_properties()

        assert isinstance(typed_props, LanceDBConfigProperties)
        assert typed_props.table_schema_version == LanceDBTableSchemaVersion.V1
        assert typed_props.vector_index_type == "bruteforce"

    def test_vector_store_config_inherits_from_kiln_parented_model(self):
        """Test that VectorStoreConfig inherits from KilnParentedModel."""
        config = VectorStoreConfig(
            name="test_store",
            store_type=VectorStoreType.LANCE_DB,
            properties={
                "table_schema_version": "1",
                "vector_index_type": "bruteforce",
            },
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
    def test_vector_store_config_valid_names(self, name):
        """Test VectorStoreConfig accepts valid names."""
        config = VectorStoreConfig(
            name=name,
            store_type=VectorStoreType.LANCE_DB,
            properties={
                "table_schema_version": "1",
                "vector_index_type": "bruteforce",
            },
        )
        assert config.name == name

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "a" * 121,  # Too long
        ],
    )
    def test_vector_store_config_invalid_names(self, name):
        """Test VectorStoreConfig rejects invalid names."""
        with pytest.raises(ValidationError):
            VectorStoreConfig(
                name=name,
                store_type=VectorStoreType.LANCE_DB,
                properties={
                    "table_schema_version": "1",
                    "vector_index_type": "bruteforce",
                },
            )
