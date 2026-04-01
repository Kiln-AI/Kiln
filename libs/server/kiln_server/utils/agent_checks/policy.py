from typing import Literal

from pydantic import BaseModel, model_validator


class AgentPolicy(BaseModel):
    permission: Literal["allow", "deny"]
    requires_approval: bool
    approval_description: str | None = None

    @model_validator(mode="after")
    def validate_approval_fields(self) -> "AgentPolicy":
        if self.permission == "deny" and self.requires_approval:
            raise ValueError("Denied endpoints cannot require approval")
        if self.requires_approval and (
            not self.approval_description or not self.approval_description.strip()
        ):
            raise ValueError(
                "approval_description is required when requires_approval is True"
            )
        if not self.requires_approval and self.approval_description is not None:
            raise ValueError(
                "approval_description must be None when requires_approval is False"
            )
        return self


_DENY_POLICY = AgentPolicy(permission="deny", requires_approval=False)
_ALLOW_POLICY = AgentPolicy(permission="allow", requires_approval=False)

DENY_AGENT: dict = {"x-agent-policy": _DENY_POLICY.model_dump(exclude_none=True)}
ALLOW_AGENT: dict = {"x-agent-policy": _ALLOW_POLICY.model_dump(exclude_none=True)}


def agent_policy_require_approval(description: str) -> dict:
    if not description or not description.strip():
        raise ValueError("description must be a non-empty string")
    policy = AgentPolicy(
        permission="allow",
        requires_approval=True,
        approval_description=description,
    )
    return {"x-agent-policy": policy.model_dump(exclude_none=True)}
