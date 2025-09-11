from typing import Any, TypeVar, Union

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
