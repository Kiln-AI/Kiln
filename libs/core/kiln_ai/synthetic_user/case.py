"""SyntheticUserCase — input contract for the multi-turn SU runner.

Two-field shape: `seed_prompt` (the opening user message) and
`synthetic_user_info` (an opaque tagged blob; the runner parses it into a
typed SyntheticUserInfo before building the SyntheticUserDriver).

Callers holding a serialized case convert it to this model before
invoking the runner.
"""

from pydantic import BaseModel, Field

from kiln_ai.datamodel.openenv import OpenEnvReset


class SyntheticUserCase(BaseModel):
    """One case for the multi-turn SU drive loop.

    `seed_prompt` is the first user-side message sent into the target
    task. `synthetic_user_info` is the persona/goal/behavior_guidance
    blob, parsed by the caller into the typed SyntheticUserInfo the
    driver builds the SU's system prompt from.
    """

    seed_prompt: str = Field(..., min_length=1)
    synthetic_user_info: str = Field(..., min_length=1)
    openenv_reset: OpenEnvReset | None = Field(
        default=None,
        description="The OpenEnv episode a grounded case runs in. Every turn of the case runs in one episode started from this reset. None drives the case as its run config would run on its own.",
    )
    judge_guidance: str | None = Field(
        default=None,
        description="A grounded case's answer key, as markdown. When set, the synthetic user knows that what its persona and goal name exists, so it doesn't accept a not-found reply.",
    )
