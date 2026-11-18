import pytest
from pydantic import Field, ValidationError

from kiln_ai.datamodel.basemodel import KilnParentedModel, KilnParentModel


class ModelC(KilnParentedModel):
    code: str = Field(..., pattern=r"^[A-Z]{3}$")

    @classmethod
    def relationship_name(cls) -> str:
        return "cs"

    @classmethod
    def parent_type(cls):
        return ModelB


class ModelB(KilnParentedModel, KilnParentModel, parent_of={"cs": ModelC}):
    value: int = Field(..., ge=0)

    @classmethod
    def relationship_name(cls) -> str:
        return "bs"

    @classmethod
    def parent_type(cls):
        return ModelA


# Define the hierarchy
class ModelA(KilnParentModel, parent_of={"bs": ModelB}):
    name: str = Field(..., min_length=3)


def test_validation_error_in_c_level():
    data = {
        "name": "Root",
        "bs": [
            {
                "value": 10,
                "cs": [
                    {"code": "ABC"},
                    {"code": "DEF"},
                    {"code": "invalid"},  # This should cause a validation error
                ],
            }
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        ModelA.validate_and_save_with_subrelations(data)

    assert "String should match pattern" in str(exc_info.value)


def test_persist_three_level_hierarchy(tmp_path):
    # Set up temporary paths
    root_path = tmp_path / "model_a.kiln"

    data = {
        "name": "Root",
        "bs": [
            {"value": 10, "cs": [{"code": "ABC"}, {"code": "DEF"}]},
            {"value": 20, "cs": [{"code": "XYZ"}]},
        ],
    }

    instance = ModelA.validate_and_save_with_subrelations(data, path=root_path)

    assert isinstance(instance, ModelA)
    assert instance.name == "Root"
    assert instance.path == root_path
    assert len(instance.bs()) == 2

    # Load the instance back from the file to double-check
    instance = ModelA.load_from_file(root_path)

    bs = instance.bs()
    assert len(bs) == 2

    # Check for the existence of both expected B models
    b_values = [b.value for b in bs]
    assert 10 in b_values
    assert 20 in b_values

    # Find the B models by their values
    b10 = next(b for b in bs if b.value == 10)
    b20 = next(b for b in bs if b.value == 20)

    assert len(b10.cs()) == 2
    assert len(b20.cs()) == 1

    # Check C models for b10
    c_codes_b10 = [c.code for c in b10.cs()]
    assert "ABC" in c_codes_b10
    assert "DEF" in c_codes_b10

    # Check C model for b20
    c_codes_b20 = [c.code for c in b20.cs()]
    assert "XYZ" in c_codes_b20

    # Check that all objects have their parent set correctly
    assert all(b.parent == instance for b in bs)
    assert all(c.parent.id == b10.id for c in b10.cs())
    assert all(c.parent.id == b20.id for c in b20.cs())


def test_persist_model_a_without_children(tmp_path):
    # Set up temporary path
    root_path = tmp_path / "model_a_no_children.kiln"

    data = {"name": "RootNoChildren"}

    instance = ModelA.validate_and_save_with_subrelations(data, path=root_path)

    assert isinstance(instance, ModelA)
    assert instance.name == "RootNoChildren"
    assert instance.path == root_path
    assert len(instance.bs()) == 0

    # Verify that the file was created
    assert root_path.exists()

    # Load the instance back from the file to double-check
    loaded_instance = ModelA.load_from_file(root_path)
    assert loaded_instance.name == "RootNoChildren"
    assert len(loaded_instance.bs()) == 0


def test_validate_without_saving(tmp_path):
    data = {
        "name": "ValidateOnly",
        "bs": [
            {"value": 30, "cs": [{"code": "GHI"}, {"code": "JKL"}]},
            {"value": 40, "cs": [{"code": "MNO"}]},
        ],
    }

    # Validate the data without saving
    ModelA._validate_nested(data, save=False)

    data = {
        "name": "ValidateOnly",
        "bs": [
            {"value": 30, "cs": [{"code": "GHI"}, {"code": "JKL"}]},
            {"value": 40, "cs": [{"code": 123}]},
        ],
    }

    with pytest.raises(ValidationError):
        ModelA._validate_nested(data, save=False)


def test_validation_error_in_multiple_levels():
    data = {
        "missing_name": "Root",
        "bs": [
            {
                "value": -1,
                "cs": [
                    {"code": "ABC"},
                    {"code": "DEF"},
                    {"code": "invalid"},
                ],
            }
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        ModelA.validate_and_save_with_subrelations(data)

    assert len(exc_info.value.errors()) == 3

    first = exc_info.value.errors()[0]
    assert "Field required" in first["msg"]
    assert first["loc"] == ("name",)

    second = exc_info.value.errors()[1]
    assert "Input should be greater than or equal to 0" in second["msg"]
    assert second["loc"] == ("bs", 0, "value")

    third = exc_info.value.errors()[2]
    assert "String should match pattern" in third["msg"]
    assert third["loc"] == ("bs", 0, "cs", 2, "code")


def test_validation_error_in_c_level_length():
    data = {
        "name": "Root",
        "bs": [
            {
                "value": 10,
                "cs": [
                    {"code": "ABC"},
                    {"code": "DEF"},
                    {"code": "GE"},  # This should cause a validation error
                ],
            }
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        ModelA.validate_and_save_with_subrelations(data)

    assert "String should match pattern" in str(exc_info.value)


@pytest.mark.parametrize(
    "data, expected",
    [
        ({"name": "Root", "bs": [{"value": 1, "cs": [{"code": "ABC"}]}]}, []),
        ({"name": "Root", "path": "a.kiln", "parent": None}, ["path", "parent"]),
        (
            {
                "name": "Root",
                "bs": [
                    {"value": 1},
                    {
                        "value": 2,
                        "path": "b.kiln",
                        "cs": [{"code": "ABC"}, {"code": "DEF", "parent": {}}],
                    },
                ],
            },
            ["bs[1].path", "bs[1].cs[1].parent"],
        ),
        # A child's id names its folder; the top-level id is left to the caller.
        (
            {
                "name": "Root",
                "id": "root",
                "bs": [{"value": 1, "id": "../b", "cs": [{"code": "ABC", "id": "/c"}]}],
            },
            ["bs[0].id", "bs[0].cs[0].id"],
        ),
        # Malformed relationships are left for the save to reject.
        ({"name": "Root", "bs": "not a list"}, []),
        ({"name": "Root", "bs": ["not a dict"]}, []),
        ({"name": "Root", "not_a_relationship": [{"path": "x.kiln"}]}, []),
    ],
)
def test_find_save_location_fields(data, expected):
    assert ModelA.find_save_location_fields(data) == expected
