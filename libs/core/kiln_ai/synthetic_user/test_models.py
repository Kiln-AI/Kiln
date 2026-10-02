"""Unit tests for SyntheticUserInfo."""

import pytest
from pydantic import ValidationError

from kiln_ai.synthetic_user.models import SyntheticUserInfo


def test_synthetic_user_info_required_fields() -> None:
    info = SyntheticUserInfo(persona="p", goal="g")
    assert info.persona == "p"
    assert info.goal == "g"
    assert info.behavior_guidance is None


def test_synthetic_user_info_accepts_behavior_guidance() -> None:
    info = SyntheticUserInfo(persona="p", goal="g", behavior_guidance="b")
    assert info.behavior_guidance == "b"


def test_synthetic_user_info_rejects_missing_persona() -> None:
    with pytest.raises(ValidationError):
        SyntheticUserInfo(goal="g")  # type: ignore[call-arg]


def test_synthetic_user_info_rejects_missing_goal() -> None:
    with pytest.raises(ValidationError):
        SyntheticUserInfo(persona="p")  # type: ignore[call-arg]
