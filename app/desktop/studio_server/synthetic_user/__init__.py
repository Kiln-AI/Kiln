"""Studio_server-side wrapper for the kiln_server synthetic-user `/generate`
endpoint, plus the multi-turn synthetic-data-generation drive loop.

Per-turn synthetic-user invocation itself lives in
`libs/core/kiln_ai/synthetic_user/` (calls the LLM with the user's keys);
this module covers only the authoring HTTP call and the runner that
orchestrates target invocation + SU response across multiple cases.
"""

from app.desktop.studio_server.synthetic_user.client import (
    SyntheticUserClient,
    SyntheticUserError,
    SyntheticUserRequestError,
    SyntheticUserServerError,
)

__all__ = [
    "SyntheticUserClient",
    "SyntheticUserError",
    "SyntheticUserRequestError",
    "SyntheticUserServerError",
]
