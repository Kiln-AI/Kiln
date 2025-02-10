from typing import NoReturn


# Weird trick, but passing a enum to NoReturn triggers the type checker to complain unless all values are handled.
def raise_exhaustive_enum_error(value: NoReturn) -> NoReturn:
    raise ValueError(f"Unhandled enum value: {value}")
