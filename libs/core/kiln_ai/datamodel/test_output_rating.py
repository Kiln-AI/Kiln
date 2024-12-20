import json

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel import RequirementRating, TaskOutputRating, TaskOutputRatingType


def test_valid_task_output_rating():
    rating = TaskOutputRating(value=4.0, requirement_ratings={"req1": 5.0, "req2": 3.0})
    assert rating.type == TaskOutputRatingType.five_star
    assert rating.value == 4.0
    dumped = json.loads(rating.model_dump_json())
    assert dumped["requirement_ratings"] == {
        "req1": {"type": TaskOutputRatingType.five_star, "value": 5.0},
        "req2": {"type": TaskOutputRatingType.five_star, "value": 3.0},
    }

    # new format
    rating = TaskOutputRating(
        value=4.0,
        requirement_ratings={
            "req1": {"type": TaskOutputRatingType.five_star, "value": 5.0},
            "req2": {"type": TaskOutputRatingType.five_star, "value": 3.0},
        },
    )
    dumped = json.loads(rating.model_dump_json())
    assert dumped["requirement_ratings"] == {
        "req1": {"type": TaskOutputRatingType.five_star, "value": 5.0},
        "req2": {"type": TaskOutputRatingType.five_star, "value": 3.0},
    }


def test_invalid_rating_type():
    with pytest.raises(ValidationError, match="Input should be"):
        TaskOutputRating(type="invalid_type", value=4.0)


def test_invalid_rating_value():
    with pytest.raises(
        ValidationError,
        match="Overall rating of type five_star must be an integer value",
    ):
        TaskOutputRating(value=3.5)


def test_rating_out_of_range():
    with pytest.raises(
        ValidationError,
        match="Overall rating of type five_star must be between 1 and 5 stars",
    ):
        TaskOutputRating(value=6.0)


def test_rating_below_range():
    with pytest.raises(
        ValidationError,
        match="Overall rating of type five_star must be between 1 and 5 stars",
    ):
        TaskOutputRating(value=0.0)


def test_valid_requirement_ratings_old_format():
    rating = TaskOutputRating.model_validate(
        {"value": 4.0, "requirement_ratings": {"req1": 5.0, "req2": 3.0, "req3": 1.0}}
    )
    dumped = json.loads(rating.model_dump_json())
    assert dumped["requirement_ratings"] == {
        "req1": {"type": TaskOutputRatingType.five_star, "value": 5.0},
        "req2": {"type": TaskOutputRatingType.five_star, "value": 3.0},
        "req3": {"type": TaskOutputRatingType.five_star, "value": 1.0},
    }


def test_valid_requirement_ratings_new_format():
    rating = TaskOutputRating.model_validate(
        {
            "value": 4.0,
            "requirement_ratings": {
                "req1": {"type": TaskOutputRatingType.five_star, "value": 5.0},
                "req2": {"type": TaskOutputRatingType.five_star, "value": 3.0},
                "req3": {"type": TaskOutputRatingType.five_star, "value": 1.0},
            },
        }
    )
    dumped = json.loads(rating.model_dump_json())
    assert dumped["requirement_ratings"] == {
        "req1": {"type": TaskOutputRatingType.five_star, "value": 5.0},
        "req2": {"type": TaskOutputRatingType.five_star, "value": 3.0},
        "req3": {"type": TaskOutputRatingType.five_star, "value": 1.0},
    }


def test_invalid_requirement_rating_value():
    with pytest.raises(
        ValidationError,
        match="Requirement rating for req id: req1 of type five_star must be an integer value",
    ):
        TaskOutputRating(value=4.0, requirement_ratings={"req1": 3.5})

    # new format
    with pytest.raises(
        ValidationError,
        match="Requirement rating for req id: req1 of type five_star must be an integer value",
    ):
        TaskOutputRating(
            value=4.0,
            requirement_ratings={
                "req1": {"type": TaskOutputRatingType.five_star, "value": 3.5}
            },
        )


def test_requirement_rating_out_of_range():
    with pytest.raises(
        ValidationError,
        match="Requirement rating for req id: req1 of type five_star must be between 1 and 5 stars",
    ):
        TaskOutputRating(value=4.0, requirement_ratings={"req1": 6.0})

    # new format
    with pytest.raises(
        ValidationError,
        match="Requirement rating for req id: req1 of type five_star must be between 1 and 5 stars",
    ):
        TaskOutputRating(
            value=4.0,
            requirement_ratings={
                "req1": {"type": TaskOutputRatingType.five_star, "value": 6.0}
            },
        )


def test_empty_requirement_ratings():
    rating = TaskOutputRating(value=4.0)
    assert rating.requirement_ratings == {}


def test_empty_requirement_ratings_integer():
    rating = TaskOutputRating(
        value=4,
        requirement_ratings={
            "req1": RequirementRating(type=TaskOutputRatingType.five_star, value=5),
        },
    )
    assert rating.requirement_ratings["req1"].value == 5.0


def test_invalid_id_type():
    with pytest.raises(ValidationError):
        TaskOutputRating(
            value=4.0,
            requirement_ratings={
                123: 4.0  # Assuming ID_TYPE is str
            },
        )

    # new format
    with pytest.raises(ValidationError):
        TaskOutputRating(
            value=4.0,
            requirement_ratings={
                123: {"type": TaskOutputRatingType.five_star, "value": 4.0}
            },
        )


def test_valid_custom_rating():
    rating = TaskOutputRating(
        type=TaskOutputRatingType.custom,
        value=31.459,
        requirement_ratings={
            "req1": {"type": TaskOutputRatingType.custom, "value": 42.0},
            "req2": {"type": TaskOutputRatingType.custom, "value": 3.14},
        },
    )
    assert rating.type == TaskOutputRatingType.custom
    assert rating.value == 31.459
    dumped = json.loads(rating.model_dump_json())
    assert dumped["requirement_ratings"] == {
        "req1": {"type": TaskOutputRatingType.custom, "value": 42.0},
        "req2": {"type": TaskOutputRatingType.custom, "value": 3.14},
    }


# We upgraded the format of requirement_ratings to be a dict of RequirementRating objects from a dict of floats
def test_task_output_rating_format_upgrade():
    # Test old format (dict of floats)
    old_format = {
        "type": "five_star",
        "value": 4.0,
        "requirement_ratings": {"req1": 5.0, "req2": 3.0},
    }

    rating = TaskOutputRating.model_validate(old_format)

    # Verify the upgrade worked
    assert isinstance(rating.requirement_ratings["req1"], RequirementRating)
    assert rating.requirement_ratings["req1"].value == 5.0
    assert rating.requirement_ratings["req1"].type == TaskOutputRatingType.five_star
    assert rating.requirement_ratings["req2"].value == 3.0
    assert rating.requirement_ratings["req2"].type == TaskOutputRatingType.five_star

    # Verify the json dump is new format
    json_dump = json.loads(rating.model_dump_json())
    assert json_dump["requirement_ratings"]["req1"]["type"] == "five_star"
    assert json_dump["requirement_ratings"]["req1"]["value"] == 5.0
    assert json_dump["requirement_ratings"]["req2"]["type"] == "five_star"
    assert json_dump["requirement_ratings"]["req2"]["value"] == 3.0

    # Test new format (dict of RequirementRating)
    new_format = {
        "type": "five_star",
        "value": 4.0,
        "requirement_ratings": {
            "req1": {"value": 5.0, "type": "five_star"},
            "req2": {"value": 3.0, "type": "five_star"},
        },
    }

    rating = TaskOutputRating.model_validate(new_format)

    # Verify new format works as expected
    assert isinstance(rating.requirement_ratings["req1"], RequirementRating)
    assert rating.requirement_ratings["req1"].value == 5.0
    assert rating.requirement_ratings["req1"].type == TaskOutputRatingType.five_star

    # Verify the json dump is new format
    json_dump = json.loads(rating.model_dump_json())
    assert json_dump["requirement_ratings"]["req1"]["type"] == "five_star"
    assert json_dump["requirement_ratings"]["req1"]["value"] == 5.0
    assert json_dump["requirement_ratings"]["req2"]["type"] == "five_star"
    assert json_dump["requirement_ratings"]["req2"]["value"] == 3.0

    # Test mixed format (should fail)
    mixed_format = {
        "type": "five_star",
        "value": 4.0,
        "requirement_ratings": {
            "req1": 5.0,
            "req2": {"value": 3.0, "type": "five_star"},
        },
    }

    with pytest.raises(ValidationError):
        TaskOutputRating.model_validate(mixed_format)

    # Test empty requirement_ratings
    empty_format = {"type": "five_star", "value": 4.0, "requirement_ratings": {}}

    rating = TaskOutputRating.model_validate(empty_format)
    assert rating.requirement_ratings == {}


def test_valid_pass_fail_rating():
    rating = TaskOutputRating(
        type=TaskOutputRatingType.pass_fail,
        value=1.0,
        requirement_ratings={
            "req1": {"type": TaskOutputRatingType.pass_fail, "value": 1.0},
            "req2": {"type": TaskOutputRatingType.pass_fail, "value": 0.0},
        },
    )
    assert rating.type == TaskOutputRatingType.pass_fail
    assert rating.value == 1.0
    dumped = json.loads(rating.model_dump_json())
    assert dumped["requirement_ratings"] == {
        "req1": {"type": TaskOutputRatingType.pass_fail, "value": 1.0},
        "req2": {"type": TaskOutputRatingType.pass_fail, "value": 0.0},
    }


def test_invalid_pass_fail_rating_value():
    with pytest.raises(
        ValidationError,
        match="Overall rating of type pass_fail must be an integer value",
    ):
        TaskOutputRating(type=TaskOutputRatingType.pass_fail, value=0.5)

    with pytest.raises(
        ValidationError,
        match="Requirement rating for req id: req1 of type pass_fail must be an integer value",
    ):
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail,
            value=1.0,
            requirement_ratings={
                "req1": {"type": TaskOutputRatingType.pass_fail, "value": 0.5}
            },
        )


def test_pass_fail_rating_out_of_range():
    with pytest.raises(
        ValidationError,
        match="Overall rating of type pass_fail must be 0 \\(fail\\) or 1 \\(pass\\)",
    ):
        TaskOutputRating(type=TaskOutputRatingType.pass_fail, value=2.0)

    with pytest.raises(
        ValidationError,
        match="Requirement rating for req id: req1 of type pass_fail must be 0 \\(fail\\) or 1 \\(pass\\)",
    ):
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail,
            value=1.0,
            requirement_ratings={
                "req1": {"type": TaskOutputRatingType.pass_fail, "value": 2.0}
            },
        )


def test_valid_pass_fail_critical_rating():
    rating = TaskOutputRating(
        type=TaskOutputRatingType.pass_fail_critical,
        value=1.0,
        requirement_ratings={
            "req1": {"type": TaskOutputRatingType.pass_fail_critical, "value": 1.0},
            "req2": {"type": TaskOutputRatingType.pass_fail_critical, "value": 0.0},
            "req3": {"type": TaskOutputRatingType.pass_fail_critical, "value": -1.0},
        },
    )
    assert rating.type == TaskOutputRatingType.pass_fail_critical
    assert rating.value == 1.0
    dumped = json.loads(rating.model_dump_json())
    assert dumped["requirement_ratings"] == {
        "req1": {"type": TaskOutputRatingType.pass_fail_critical, "value": 1.0},
        "req2": {"type": TaskOutputRatingType.pass_fail_critical, "value": 0.0},
        "req3": {"type": TaskOutputRatingType.pass_fail_critical, "value": -1.0},
    }


def test_invalid_pass_fail_critical_rating_value():
    with pytest.raises(
        ValidationError,
        match="Overall rating of type pass_fail_critical must be an integer value",
    ):
        TaskOutputRating(type=TaskOutputRatingType.pass_fail_critical, value=0.5)

    with pytest.raises(
        ValidationError,
        match="Requirement rating for req id: req1 of type pass_fail_critical must be an integer value",
    ):
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail_critical,
            value=1.0,
            requirement_ratings={
                "req1": {"type": TaskOutputRatingType.pass_fail_critical, "value": 0.5}
            },
        )


def test_pass_fail_critical_rating_out_of_range():
    with pytest.raises(
        ValidationError,
        match="Overall rating of type pass_fail_critical must be -1 \\(critical fail\\), 0 \\(fail\\), or 1 \\(pass\\)",
    ):
        TaskOutputRating(type=TaskOutputRatingType.pass_fail_critical, value=2.0)

    with pytest.raises(
        ValidationError,
        match="Requirement rating for req id: req1 of type pass_fail_critical must be -1 \\(critical fail\\), 0 \\(fail\\), or 1 \\(pass\\)",
    ):
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail_critical,
            value=1.0,
            requirement_ratings={
                "req1": {"type": TaskOutputRatingType.pass_fail_critical, "value": 2.0}
            },
        )


def test_is_high_quality():
    # Test five_star ratings
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.five_star, value=5.0
        ).is_high_quality()
        is True
    )
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.five_star, value=4.0
        ).is_high_quality()
        is True
    )
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.five_star, value=3.0
        ).is_high_quality()
        is False
    )
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.five_star, value=2.0
        ).is_high_quality()
        is False
    )
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.five_star, value=1.0
        ).is_high_quality()
        is False
    )

    # Test pass_fail ratings
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail, value=1.0
        ).is_high_quality()
        is True
    )
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail, value=0.0
        ).is_high_quality()
        is False
    )

    # Test pass_fail_critical ratings
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail_critical, value=1.0
        ).is_high_quality()
        is True
    )
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail_critical, value=0.0
        ).is_high_quality()
        is False
    )
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.pass_fail_critical, value=-1.0
        ).is_high_quality()
        is False
    )

    # Test custom ratings (should always return False)
    assert (
        TaskOutputRating(
            type=TaskOutputRatingType.custom, value=100.0
        ).is_high_quality()
        is False
    )
    assert (
        TaskOutputRating(type=TaskOutputRatingType.custom, value=0.0).is_high_quality()
        is False
    )

    # Test None value
    assert (
        TaskOutputRating(type=TaskOutputRatingType.custom, value=None).is_high_quality()
        is False
    )
