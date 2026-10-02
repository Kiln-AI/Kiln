"""Local synthetic-user player.

Plays the synthetic-user side of a conversation locally, calling the LLM
with the user's own provider keys.

Public surface:

- `SyntheticUserDriver` — construct once per case, call `respond()` per turn.
- `SyntheticUserInfo` / `SyntheticUserDriverConfig` — typed configs.
- `SyntheticUserCase` — input contract for the multi-turn drive loop.
- `parse_synthetic_user_info` — tagged-blob parser.
- `SyntheticUserInfoParseError` — raised on malformed blob.
- `role_swap` — exposed for callers that drive the loop themselves.
- `drive_case_for_eval` — transient one-case drive for the eval runner.
"""

from kiln_ai.synthetic_user.case import SyntheticUserCase
from kiln_ai.synthetic_user.driver import SyntheticUserDriver
from kiln_ai.synthetic_user.eval_drive import drive_case_for_eval
from kiln_ai.synthetic_user.models import (
    SyntheticUserDriverConfig,
    SyntheticUserInfo,
)
from kiln_ai.synthetic_user.parser import (
    SyntheticUserInfoParseError,
    parse_synthetic_user_info,
)
from kiln_ai.synthetic_user.role_swap import role_swap

__all__ = [
    "SyntheticUserCase",
    "SyntheticUserDriver",
    "SyntheticUserDriverConfig",
    "SyntheticUserInfo",
    "SyntheticUserInfoParseError",
    "drive_case_for_eval",
    "parse_synthetic_user_info",
    "role_swap",
]
