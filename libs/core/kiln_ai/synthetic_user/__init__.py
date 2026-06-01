"""Local synthetic-user player.

OSS-side per-turn invocation: replaces the removed kiln_server `/respond`
HTTP endpoint. Calls the LLM using the user's own provider keys.

Public surface:

- `SyntheticUserDriver` — construct once per case, call `respond()` per turn.
- `SyntheticUserInfo` / `SyntheticUserDriverConfig` — typed configs.
- `parse_synthetic_user_info` / `build_synthetic_user_info` — tagged-blob codec.
- `SyntheticUserInfoParseError` — raised on malformed blob.
- `role_swap` — exposed for callers that drive the loop themselves.
"""

from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.synthetic_user.models import (
    SyntheticUserDriverConfig,
    SyntheticUserInfo,
    VisibleMessageRole,
)
from kiln_ai.synthetic_user.parser import (
    SyntheticUserInfoParseError,
    build_synthetic_user_info,
    parse_synthetic_user_info,
)
from kiln_ai.synthetic_user.role_swap import role_swap

__all__ = [
    "SyntheticUserDriver",
    "SyntheticUserDriverConfig",
    "SyntheticUserInfo",
    "SyntheticUserInfoParseError",
    "VisibleMessageRole",
    "build_synthetic_user_info",
    "parse_synthetic_user_info",
    "role_swap",
]
