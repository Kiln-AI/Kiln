import pytest
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    DENY_AGENT,
    AgentPolicy,
    agent_policy_require_approval,
)
from pydantic import ValidationError


class TestAgentPolicyValidation:
    def test_allow_policy_valid(self):
        policy = AgentPolicy(permission="allow", requires_approval=False)
        assert policy.permission == "allow"
        assert policy.requires_approval is False
        assert policy.approval_description is None

    def test_deny_policy_valid(self):
        policy = AgentPolicy(permission="deny", requires_approval=False)
        assert policy.permission == "deny"
        assert policy.requires_approval is False
        assert policy.approval_description is None

    def test_approval_policy_valid(self):
        policy = AgentPolicy(
            permission="allow",
            requires_approval=True,
            approval_description="Allow editing?",
        )
        assert policy.permission == "allow"
        assert policy.requires_approval is True
        assert policy.approval_description == "Allow editing?"

    def test_deny_with_approval_raises(self):
        with pytest.raises(ValidationError, match="Denied endpoints cannot require"):
            AgentPolicy(
                permission="deny",
                requires_approval=True,
                approval_description="desc",
            )

    def test_approval_without_description_raises(self):
        with pytest.raises(ValidationError, match="approval_description is required"):
            AgentPolicy(permission="allow", requires_approval=True)

    def test_approval_with_empty_description_raises(self):
        with pytest.raises(ValidationError, match="approval_description is required"):
            AgentPolicy(
                permission="allow",
                requires_approval=True,
                approval_description="",
            )

    def test_approval_with_whitespace_only_description_raises(self):
        with pytest.raises(ValidationError, match="approval_description is required"):
            AgentPolicy(
                permission="allow",
                requires_approval=True,
                approval_description="   ",
            )

    def test_description_without_approval_raises(self):
        with pytest.raises(ValidationError, match="approval_description must be None"):
            AgentPolicy(
                permission="allow",
                requires_approval=False,
                approval_description="some desc",
            )

    def test_invalid_permission_raises(self):
        with pytest.raises(ValidationError):
            AgentPolicy(permission="block", requires_approval=False)  # type: ignore[arg-type]


class TestConstants:
    def test_deny_agent_structure(self):
        assert DENY_AGENT == {
            "x-agent-policy": {
                "permission": "deny",
                "requires_approval": False,
            }
        }

    def test_allow_agent_structure(self):
        assert ALLOW_AGENT == {
            "x-agent-policy": {
                "permission": "allow",
                "requires_approval": False,
            }
        }

    def test_constants_are_distinct_dicts(self):
        assert DENY_AGENT is not ALLOW_AGENT


class TestAgentPolicyRequireApproval:
    def test_valid_description(self):
        result = agent_policy_require_approval("Allow agent to edit project?")
        assert result == {
            "x-agent-policy": {
                "permission": "allow",
                "requires_approval": True,
                "approval_description": "Allow agent to edit project?",
            }
        }

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            agent_policy_require_approval("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            agent_policy_require_approval("   ")
