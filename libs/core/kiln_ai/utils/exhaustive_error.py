from typing import NoReturn

from typing_extensions import Never


# Used in exhaustiveness checks. When called, this branch should be unreachable.
def raise_exhaustive_enum_error(value: Never) -> NoReturn:
    raise ValueError(f"Unhandled enum value: {value}")
