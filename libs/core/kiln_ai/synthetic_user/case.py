"""SyntheticUserCase — input contract for the multi-turn SU runner.

Two-field shape: `seed_prompt` (the opening user message) and
`synthetic_user_info` (an opaque tagged blob the SyntheticUserDriver
parses on construction).

Field-identical to the kiln_server SDK's `SyntheticUserCase`. Lives here
in libs/core so the runner has no dependency on the vendored SDK in
`app/desktop/`; studio_server's FastAPI route converts SDK case → this
case at the wire boundary.
"""

from pydantic import BaseModel, Field


class SyntheticUserCase(BaseModel):
    """One case for the multi-turn SU drive loop.

    `seed_prompt` is the first user-side message sent into the target
    task. `synthetic_user_info` is the persona/goal/behavior_guidance
    blob the driver parses to build the SU's system prompt.
    """

    seed_prompt: str = Field(..., min_length=1)
    synthetic_user_info: str = Field(..., min_length=1)
