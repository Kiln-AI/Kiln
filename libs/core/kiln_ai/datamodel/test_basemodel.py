import datetime
import json
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel import Task, TaskRun
from kiln_ai.datamodel.basemodel import (
    KilnBaseModel,
    KilnParentedModel,
    string_to_valid_name,
)
from kiln_ai.datamodel.model_cache import ModelCache
from kiln_ai.datamodel.task import RunConfig


@pytest.fixture
def test_base_file(tmp_path) -> Path:
    test_file_path = tmp_path / "test_model.json"
    data = {"v": 1, "model_type": "kiln_base_model"}

    with open(test_file_path, "w") as file:
        json.dump(data, file, indent=4)

    return test_file_path


@pytest.fixture
def test_base_parented_file(tmp_path) -> Path:
    test_file_path = tmp_path / "test_model.json"
    data = {"v": 1, "model_type": "base_parent_example"}

    with open(test_file_path, "w") as file:
        json.dump(data, file, indent=4)

    return test_file_path


@pytest.fixture
def test_newer_file(tmp_path) -> Path:
    test_file_path = tmp_path / "test_model_sv.json"
    data = {"v": 99}

    with open(test_file_path, "w") as file:
        json.dump(data, file, indent=4)

    return test_file_path


@pytest.fixture
def tmp_model_cache():
    temp_cache = ModelCache()
    # We're testing integration, not cache functions, in this file
    temp_cache._enabled = True
    with (
        patch("kiln_ai.datamodel.basemodel.ModelCache.shared", return_value=temp_cache),
    ):
        yield temp_cache


def test_load_from_file(test_base_file):
    model = KilnBaseModel.load_from_file(test_base_file)
    assert model.v == 1
    assert model.path == test_base_file


def test_save_to_file(test_base_file):
    model = KilnBaseModel(path=test_base_file)
    model.save_to_file()

    with open(test_base_file, "r") as file:
        data = json.load(file)

    assert data["v"] == 1
    assert data["model_type"] == "kiln_base_model"


def test_save_to_file_without_path():
    model = KilnBaseModel()
    with pytest.raises(ValueError):
        model.save_to_file()


def test_max_schema_version(test_newer_file):
    with pytest.raises(ValueError):
        KilnBaseModel.load_from_file(test_newer_file)


def test_type_name():
    model = KilnBaseModel()
    assert model.model_type == "kiln_base_model"


def test_created_atby():
    model = KilnBaseModel()
    assert model.created_at is not None
    # Check it's within 2 seconds of now
    now = datetime.datetime.now()
    assert abs((model.created_at - now).total_seconds()) < 2

    # Created by
    assert len(model.created_by) > 0
    # assert model.created_by == "scosman"


# Instance of the parented model for abstract methods
class NamedParentedModel(KilnParentedModel):
    @classmethod
    def relationship_name(cls) -> str:
        return "tests"

    @classmethod
    def parent_type(cls):
        return KilnBaseModel


def test_parented_model_path_gen(tmp_path):
    parent = KilnBaseModel(path=tmp_path)
    assert parent.id is not None
    child = NamedParentedModel(parent=parent)
    child_path = child.build_path()
    assert child_path.name == "named_parented_model.kiln"
    assert child_path.parent.name == child.id
    assert child_path.parent.parent.name == "tests"
    assert child_path.parent.parent.parent == tmp_path.parent


class BaseParentExample(KilnBaseModel):
    name: Optional[str] = None


# Instance of the parented model for abstract methods, with default name builder
class DefaultParentedModel(KilnParentedModel):
    name: Optional[str] = None

    @classmethod
    def relationship_name(self):
        return "children"

    @classmethod
    def parent_type(cls):
        return BaseParentExample


def test_build_default_child_filename(tmp_path):
    parent = BaseParentExample(path=tmp_path)
    child = DefaultParentedModel(parent=parent)
    child_path = child.build_path()
    assert child_path.name == "default_parented_model.kiln"
    assert child_path.parent.name == child.id
    assert child_path.parent.parent.name == "children"
    assert child_path.parent.parent.parent == tmp_path.parent
    # now with name
    child = DefaultParentedModel(parent=parent, name="Name")
    child_path = child.build_path()
    assert child_path.name == "default_parented_model.kiln"
    assert child_path.parent.name == child.id + " - Name"
    assert child_path.parent.parent.name == "children"
    assert child_path.parent.parent.parent == tmp_path.parent


def test_serialize_child(tmp_path):
    parent = BaseParentExample(path=tmp_path)
    child = DefaultParentedModel(parent=parent, name="Name")

    expected_path = child.build_path()
    assert child.path is None
    child.save_to_file()

    # ensure we save exact path
    assert child.path is not None
    assert child.path == expected_path

    # should have made the directory, and saved the file
    with open(child.path, "r") as file:
        data = json.load(file)

    assert data["v"] == 1
    assert data["name"] == "Name"
    assert data["model_type"] == "default_parented_model"
    assert len(data["id"]) == 12
    assert child.path.parent.name == child.id + " - Name"
    assert child.path.parent.parent.name == "children"
    assert child.path.parent.parent.parent == tmp_path.parent

    # change name, see it serializes, but path stays the same
    child.name = "Name2"
    child.save_to_file()
    assert child.path == expected_path
    with open(child.path, "r") as file:
        data = json.load(file)
    assert data["name"] == "Name2"


def test_save_to_set_location(tmp_path):
    # Keeps the OG path if parent and path are both set
    parent = BaseParentExample(path=tmp_path)
    child_path = tmp_path.parent / "child.kiln"
    child = DefaultParentedModel(path=child_path, parent=parent, name="Name")
    assert child.build_path() == child_path

    # check file created at child_path, not the default smart path
    assert not child_path.exists()
    child.save_to_file()
    assert child_path.exists()

    # if we don't set the path, use the parent + smartpath
    child2 = DefaultParentedModel(parent=parent, name="Name2")
    assert child2.build_path().parent.name == child2.id + " - Name2"
    assert child2.build_path().parent.parent.name == "children"
    assert child2.build_path().parent.parent.parent == tmp_path.parent


def test_parent_without_path():
    # no path from parent or direct path
    parent = BaseParentExample()
    child = DefaultParentedModel(parent=parent, name="Name")
    with pytest.raises(ValueError):
        child.save_to_file()


def test_parent_wrong_type():
    # DefaultParentedModel is parented to BaseParentExample, not KilnBaseModel
    parent = KilnBaseModel()
    with pytest.raises(ValueError):
        DefaultParentedModel(parent=parent, name="Name")


def test_load_children(test_base_parented_file):
    # Set up parent and children models
    parent = BaseParentExample.load_from_file(test_base_parented_file)

    child1 = DefaultParentedModel(parent=parent, name="Child1")
    child2 = DefaultParentedModel(parent=parent, name="Child2")
    child3 = DefaultParentedModel(parent=parent, name="Child3")

    # Ensure the children are saved correctly
    child1.save_to_file()
    child2.save_to_file()
    child3.save_to_file()

    # Load children from parent path
    children = DefaultParentedModel.all_children_of_parent_path(test_base_parented_file)

    # Verify that all children are loaded correctly
    assert len(children) == 3
    names = [child.name for child in children]
    assert "Child1" in names
    assert "Child2" in names
    assert "Child3" in names
    assert all(child.model_type == "default_parented_model" for child in children)


def test_base_filename():
    model = DefaultParentedModel(name="Test")
    assert model.base_filename() == "default_parented_model.kiln"
    model = NamedParentedModel(name="Test")
    assert model.base_filename() == "named_parented_model.kiln"
    assert NamedParentedModel.base_filename() == "named_parented_model.kiln"


def test_load_from_folder(test_base_parented_file):
    parent = BaseParentExample.load_from_file(test_base_parented_file)
    child1 = DefaultParentedModel(parent=parent, name="Child1")
    child1.save_to_file()

    loaded_child1 = DefaultParentedModel.load_from_folder(child1.path.parent)
    assert loaded_child1.name == "Child1"


def test_lazy_load_parent(tmp_path):
    # Create a parent
    parent = BaseParentExample(
        name="Parent", path=(tmp_path / BaseParentExample.base_filename())
    )
    parent.save_to_file()

    # Create a child
    child = DefaultParentedModel(parent=parent, name="Child")
    child.save_to_file()

    # Load the child by path
    loaded_child = DefaultParentedModel.load_from_file(child.path)

    # Access the parent to trigger lazy loading
    loaded_parent = loaded_child.parent

    # Verify that the parent is now loaded and correct
    assert loaded_parent is not None
    assert loaded_parent.name == "Parent"
    assert loaded_parent.path == parent.path

    # Verify that the parent is cached
    assert loaded_child.cached_parent() is loaded_parent


def test_delete(tmp_path):
    # Test deleting a file
    file_path = tmp_path / "test.kiln"
    model = KilnBaseModel(path=file_path)
    model.save_to_file()
    assert file_path.exists()
    model.delete()
    assert not file_path.exists()
    assert not file_path.parent.exists()
    assert model.path is None


def test_delete_dir(tmp_path):
    # Test deleting a directory
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir(parents=True)
    model = KilnBaseModel(path=dir_path)
    assert dir_path.exists()
    model.delete()
    assert not dir_path.exists()
    assert model.path is None


def test_delete_no_path():
    # Test deleting with no path
    model = KilnBaseModel()
    with pytest.raises(ValueError, match="Cannot delete model because path is not set"):
        model.delete()


def test_string_to_valid_name():
    # Test basic valid strings remain unchanged
    assert string_to_valid_name("Hello World") == "Hello World"
    assert string_to_valid_name("Test-123") == "Test-123"
    assert string_to_valid_name("my_file_name") == "my_file_name"

    # Test invalid characters are replaced
    assert string_to_valid_name("Hello@World!") == "Hello_World"
    assert string_to_valid_name("File.name.txt") == "File_name_txt"
    assert string_to_valid_name("Special#$%Chars") == "Special_Chars"

    # Test consecutive invalid characters
    assert string_to_valid_name("multiple!!!symbols") == "multiple_symbols"
    assert string_to_valid_name("path/to/file") == "path_to_file"

    # Test leading/trailing special characters
    assert string_to_valid_name("__test__") == "test"
    assert string_to_valid_name("...test...") == "test"

    # Test empty string and whitespace
    assert string_to_valid_name("") == ""
    assert string_to_valid_name("   ") == ""


def test_load_from_file_with_cache(test_base_file, tmp_model_cache):
    tmp_model_cache.get_model = MagicMock(return_value=None)
    tmp_model_cache.set_model = MagicMock()

    # Load the model
    model = KilnBaseModel.load_from_file(test_base_file)

    # Check that the cache was checked and set
    tmp_model_cache.get_model.assert_called_once_with(
        test_base_file, KilnBaseModel, readonly=False
    )
    tmp_model_cache.set_model.assert_called_once()

    # Ensure the model is correctly loaded
    assert model.v == 1
    assert model.path == test_base_file


def test_save_to_file_invalidates_cache(test_base_file, tmp_model_cache):
    # Create and save the model
    model = KilnBaseModel(path=test_base_file)

    # Set mock after to ignore any previous calls, we want to see save calls it
    tmp_model_cache.invalidate = MagicMock()
    model.save_to_file()

    # Check that the cache was invalidated. Might be called multiple times for setting props like path. but must be called at least once.
    tmp_model_cache.invalidate.assert_called_with(test_base_file)


def test_delete_invalidates_cache(tmp_path, tmp_model_cache):
    # Create and save the model
    file_path = tmp_path / "test.kiln"
    model = KilnBaseModel(path=file_path)
    model.save_to_file()

    # populate and check cache
    model = KilnBaseModel.load_from_file(file_path)
    cached_model = tmp_model_cache.get_model(file_path, KilnBaseModel)
    assert cached_model.id == model.id

    tmp_model_cache.invalidate = MagicMock()

    # Delete the model
    model.delete()

    # Check that the cache was invalidated
    tmp_model_cache.invalidate.assert_called_with(file_path)
    assert tmp_model_cache.get_model(file_path, KilnBaseModel) is None


def test_load_from_file_with_cached_model(test_base_file, tmp_model_cache):
    # Set up the mock to return a cached model
    cached_model = KilnBaseModel(v=1, path=test_base_file)
    tmp_model_cache.get_model = MagicMock(return_value=cached_model)

    with patch("builtins.open", create=True) as mock_open:
        # Load the model
        model = KilnBaseModel.load_from_file(test_base_file)

        # Check that the cache was checked and the cached model was returned
        tmp_model_cache.get_model.assert_called_once_with(
            test_base_file, KilnBaseModel, readonly=False
        )
        assert model is cached_model

        # Assert that open was not called (we used the cached model, not file)
        mock_open.assert_not_called()


def test_from_id_and_parent_path(test_base_parented_file, tmp_model_cache):
    # Set up parent and children models
    parent = BaseParentExample.load_from_file(test_base_parented_file)

    child1 = DefaultParentedModel(parent=parent, name="Child1")
    child2 = DefaultParentedModel(parent=parent, name="Child2")
    child3 = DefaultParentedModel(parent=parent, name="Child3")

    # Save all children
    child1.save_to_file()
    child2.save_to_file()
    child3.save_to_file()

    # Test finding existing child by ID
    found_child = DefaultParentedModel.from_id_and_parent_path(
        child2.id, test_base_parented_file
    )
    assert found_child is not None
    assert found_child.id == child2.id
    assert found_child.name == "Child2"
    assert found_child is not child2  # not same instance (deep copy)

    # Test non-existent ID returns None
    not_found = DefaultParentedModel.from_id_and_parent_path(
        "nonexistent", test_base_parented_file
    )
    assert not_found is None


def test_from_id_and_parent_path_with_cache(test_base_parented_file, tmp_model_cache):
    # Set up parent and child
    parent = BaseParentExample.load_from_file(test_base_parented_file)
    child = DefaultParentedModel(parent=parent, name="Child")
    child.save_to_file()

    # First load to populate cache
    _ = DefaultParentedModel.from_id_and_parent_path(child.id, test_base_parented_file)

    # Mock cache to verify it's used
    tmp_model_cache.get_model_id = MagicMock(return_value=child.id)

    # Load again - should use cache
    found_child = DefaultParentedModel.from_id_and_parent_path(
        child.id, test_base_parented_file
    )

    assert found_child is not None
    assert found_child.id == child.id
    tmp_model_cache.get_model_id.assert_called()


def test_from_id_and_parent_path_without_parent():
    # Test with None parent_path
    not_found = DefaultParentedModel.from_id_and_parent_path("any-id", None)
    assert not_found is None


class MockAdapter(BaseAdapter):
    """Implementation of BaseAdapter for testing"""

    async def _run(self, input):
        return RunOutput(output="test output", intermediate_outputs=None)

    def adapter_name(self) -> str:
        return "test"


@pytest.fixture
def base_task():
    return Task(name="test_task", instruction="test_instruction")


@pytest.fixture
def adapter(base_task):
    return MockAdapter(
        run_config=RunConfig(
            task=base_task,
            model_name="test_model",
            model_provider_name="test_provider",
            prompt_id="simple_prompt_builder",
        ),
    )


async def test_invoke_parsing_flow(adapter):
    # Mock dependencies
    mock_provider = MagicMock()
    mock_provider.parser = "test_parser"
    mock_provider.reasoning_capable = False

    mock_parser = MagicMock()
    mock_parser.parse_output.return_value = RunOutput(
        output="parsed test output", intermediate_outputs={"key": "value"}
    )

    mock_parser_class = MagicMock(return_value=mock_parser)

    with (
        patch.object(adapter, "model_provider", return_value=mock_provider),
        patch(
            "kiln_ai.adapters.model_adapters.base_adapter.model_parser_from_id",
            return_value=mock_parser_class,
        ),
        patch("kiln_ai.adapters.model_adapters.base_adapter.Config") as mock_config,
    ):
        # Disable autosaving for this test
        mock_config.shared.return_value.autosave_runs = False
        mock_config.shared.return_value.user_id = "test_user_id"

        # Execute
        result = await adapter.invoke("test input")

        # Verify parser was created correctly
        mock_parser_class.assert_called_once_with(structured_output=False)

        # Verify parsing occurred
        mock_parser.parse_output.assert_called_once()
        parsed_args = mock_parser.parse_output.call_args[1]
        assert isinstance(parsed_args["original_output"], RunOutput)
        assert parsed_args["original_output"].output == "test output"

        # Verify result contains parsed output
        assert isinstance(result, TaskRun)
        assert result.output.output == "parsed test output"
        assert result.intermediate_outputs == {"key": "value"}
        assert result.input == "test input"

        # Test with reasoning required, that we error if no reasoning is returned
        mock_provider.reasoning_capable = True
        with pytest.raises(
            RuntimeError,
            match="Reasoning is required for this model, but no reasoning was returned.",
        ):
            await adapter.invoke("test input")
