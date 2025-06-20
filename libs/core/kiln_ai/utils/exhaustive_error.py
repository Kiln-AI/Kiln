from typing import Any, NoReturn


# Used in exhaustiveness checks. When called, this branch should be unreachable.
def raise_exhaustive_enum_error(value: Any) -> NoReturn:
    raise ValueError(f"Unhandled enum value: {value}")
