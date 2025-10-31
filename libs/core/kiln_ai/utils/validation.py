import re
from typing import Annotated, Any, TypeVar, Union

from pydantic import AfterValidator, BeforeValidator

T = TypeVar("T")


def validate_return_dict_prop(
    dict: dict[str, Any], key: str, type: type[T], error_msg_prefix: str
) -> T:
    """
    Validate that a property exists in a dictionary and is of a specified type.

    Args:
        dict: The dictionary to validate.
        key: The key of the property to validate.
        type: The type of the property to validate.
        error_msg_prefix: The prefix of the error message.

    Returns:
        The value of the property.

    Raises:
        ValueError: If the property is not found or is not of the specified type.

    Example:
        >>> validate_return_dict_prop({"key": "value"}, "key", str, "LanceDB vector store configs properties:")
        "value"
    """
    if key not in dict:
        raise ValueError(f"{error_msg_prefix} {key} is a required property")
    if not isinstance(dict[key], type):
        raise ValueError(f"{error_msg_prefix} {key} must be of type {type}")
    return dict[key]


def validate_return_dict_prop_optional(
    dict: dict[str, Any], key: str, type: type[T], error_msg_prefix: str
) -> Union[T, None]:
    """
    Validate that a property exists in a dictionary and is of a specified type.

    Args:
        dict: The dictionary to validate.
        key: The key of the property to validate.
        type: The type of the property to validate.
        error_msg_prefix: The prefix of the error message.
    """
    if key not in dict or dict[key] is None:
        return None

    return validate_return_dict_prop(dict, key, type, error_msg_prefix)


def tool_name_validator(name: str) -> str:
    # Check if name is None or empty
    if name is None or (isinstance(name, str) and len(name.strip()) == 0):
        raise ValueError("Tool name cannot be empty")

    if not isinstance(name, str):
        raise ValueError("Tool name must be a string")

    # Check if name contains only lowercase letters, numbers, and underscores
    snake_case_regex = re.compile(r"^[a-z0-9_]+$")
    if not snake_case_regex.match(name):
        raise ValueError(
            "Tool name must be in snake_case: containing only lowercase letters (a-z), numbers (0-9), and underscores"
        )

    # Check that it doesn't start or end with underscore
    if name.startswith("_") or name.endswith("_"):
        raise ValueError("Tool name cannot start or end with an underscore")

    # Check that it doesn't have consecutive underscores
    if "__" in name:
        raise ValueError("Tool name cannot contain consecutive underscores")

    # Check that it starts with a letter (good snake_case practice)
    if not re.match(r"^[a-z]", name):
        raise ValueError("Tool name must start with a lowercase letter")

    # Check length
    if len(name) > 64:
        raise ValueError("Tool name must be less than 64 characters long")

    return name


ToolNameString = Annotated[str, BeforeValidator(tool_name_validator)]


def string_not_empty(s: str) -> str:
    if s == "":
        raise ValueError("String cannot be empty.")
    return s


NonEmptyString = Annotated[str, AfterValidator(string_not_empty)]
