import pytest

from kiln_ai.openenv.reset_schema_brief import (
    RESET_ARGUMENTS_FRAMING,
    ResetArgument,
    reset_arguments,
    reset_arguments_brief,
)

# The shape Pydantic's model_json_schema() gives a world-narrowed reset request: optional
# fields as anyOf-with-null, an enum class behind $ref, and a nested startup model.
SEAHAVEN_SHAPED_SCHEMA = {
    "$defs": {
        "ClockMode": {
            "enum": ["fixed", "tick", "running", "wall"],
            "title": "ClockMode",
            "type": "string",
        },
        "Startup": {
            "additionalProperties": False,
            "properties": {
                "acting_user": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                    "description": "Who the agent acts as: the objectId of one of the fixture's users.",
                    "title": "Acting User",
                }
            },
            "title": "Startup",
            "type": "object",
        },
    },
    "additionalProperties": False,
    "properties": {
        "seed": {
            "anyOf": [{"type": "integer"}, {"type": "null"}],
            "default": None,
            "description": "Random seed for reproducibility",
        },
        "episode_id": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "Custom episode identifier",
        },
        "fixture": {
            "anyOf": [
                {"enum": ["agency", "small_startup"], "type": "string"},
                {"type": "null"},
            ],
            "default": None,
            "description": "The fixture to start from, by id.\n\nThe fixtures:\n- `agency`: A twelve-person agency.\n- `small_startup`: A three-person startup.",
        },
        "clock_mode": {
            "anyOf": [{"$ref": "#/$defs/ClockMode"}, {"type": "null"}],
            "default": None,
            "description": "How the instance's clock moves.",
        },
        "startup": {
            "anyOf": [{"$ref": "#/$defs/Startup"}, {"type": "null"}],
            "default": None,
            "description": "The world's own startup keywords, passed to its startup hooks.",
        },
        "setup_sql": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "SQL statements, separated by ';', run against the new instance. Rows only.",
        },
    },
    "title": "SeahavenResetRequest",
    "type": "object",
}


def _paths(schema):
    return [a.path for a in reset_arguments(schema)]


def test_seahaven_shaped_schema_arguments():
    assert reset_arguments(SEAHAVEN_SHAPED_SCHEMA) == [
        ResetArgument(
            path="fixture",
            description="The fixture to start from, by id.\n\nThe fixtures:\n- `agency`: A twelve-person agency.\n- `small_startup`: A three-person startup.",
            values=["agency", "small_startup"],
        ),
        ResetArgument(
            path="clock_mode",
            description="How the instance's clock moves.",
            values=["fixed", "tick", "running", "wall"],
        ),
        ResetArgument(
            path="startup",
            description="The world's own startup keywords, passed to its startup hooks.",
            values=None,
        ),
        ResetArgument(
            path="startup.acting_user",
            description="Who the agent acts as: the objectId of one of the fixture's users.",
            values=None,
        ),
        ResetArgument(
            path="setup_sql",
            description="SQL statements, separated by ';', run against the new instance. Rows only.",
            values=None,
        ),
    ]


def test_seahaven_shaped_schema_brief():
    brief = reset_arguments_brief(SEAHAVEN_SHAPED_SCHEMA)
    assert brief is not None
    assert brief.startswith(RESET_ARGUMENTS_FRAMING)
    assert brief.endswith(
        """<openenv_server_reset_arguments>
Read from the server's reset schema. The server's owner wrote each description. Values are listed when the argument has a fixed set.
- fixture: The fixture to start from, by id.

  The fixtures:
  - `agency`: A twelve-person agency.
  - `small_startup`: A three-person startup.
  Values: agency | small_startup
- clock_mode: How the instance's clock moves.
  Values: fixed | tick | running | wall
- startup: The world's own startup keywords, passed to its startup hooks.
- startup.acting_user: Who the agent acts as: the objectId of one of the fixture's users.
- setup_sql: SQL statements, separated by ';', run against the new instance. Rows only.
</openenv_server_reset_arguments>"""
    )
    assert "seed" not in brief.split("<openenv_server_reset_arguments>")[1]
    assert "episode_id" not in brief


def test_properties_kept_in_schema_order():
    schema = {"properties": {"b": {"type": "string"}, "a": {"type": "string"}}}
    assert _paths(schema) == ["b", "a"]


def test_seed_and_episode_id_skipped_only_at_top_level():
    schema = {
        "properties": {
            "seed": {"type": "integer"},
            "episode_id": {"type": "string"},
            "options": {
                "type": "object",
                "properties": {"seed": {"type": "integer"}},
            },
        }
    }
    assert _paths(schema) == ["options.seed"]


def test_outer_description_wins_over_the_resolved_definition():
    schema = {
        "$defs": {"Mode": {"type": "string", "description": "inner", "enum": ["x"]}},
        "properties": {
            "outer": {"$ref": "#/$defs/Mode", "description": "outer"},
            "plain": {"$ref": "#/$defs/Mode"},
        },
    }
    assert reset_arguments(schema) == [
        ResetArgument("outer", "outer", ["x"]),
        ResetArgument("plain", "inner", ["x"]),
    ]


@pytest.mark.parametrize(
    "ref",
    ["#/$defs/Missing", "https://example.com/schema.json", "#/definitions/Mode"],
)
def test_unresolvable_ref_is_an_argument_with_no_structure(ref):
    schema = {
        "$defs": {"Mode": {"enum": ["x"]}},
        "properties": {"mode": {"$ref": ref, "description": "d"}},
    }
    assert reset_arguments(schema) == [ResetArgument("mode", "d", None)]


def test_cyclic_ref_stops_at_the_cycle():
    schema = {
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {"child": {"$ref": "#/$defs/Node", "description": "c"}},
            }
        },
        "properties": {"root": {"$ref": "#/$defs/Node"}},
    }
    assert reset_arguments(schema) == [ResetArgument("root.child", "c", None)]


def test_anyof_with_several_non_null_members_has_no_values():
    schema = {
        "properties": {
            "either": {
                "anyOf": [{"enum": ["a"]}, {"type": "integer"}, {"type": "null"}],
                "description": "one of two",
            }
        }
    }
    assert reset_arguments(schema) == [ResetArgument("either", "one of two", None)]


def test_undescribed_object_is_walked_but_not_listed():
    schema = {
        "properties": {
            "options": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "enum": [1, 2]},
                    "flag": {"type": "boolean", "description": "a flag"},
                },
            }
        }
    }
    assert reset_arguments(schema) == [
        ResetArgument("options.level", None, [1, 2]),
        ResetArgument("options.flag", "a flag", None),
    ]


def test_object_without_properties_is_a_leaf():
    schema = {"properties": {"extra": {"type": "object", "description": "anything"}}}
    assert reset_arguments(schema) == [ResetArgument("extra", "anything", None)]


def test_depth_is_capped_at_four():
    def nested(depth):
        if depth == 0:
            return {"type": "string", "description": "leaf"}
        return {
            "type": "object",
            "description": f"level {depth}",
            "properties": {"n": nested(depth - 1)},
        }

    schema = {"properties": {"a": nested(5)}}
    assert reset_arguments(schema) == [
        ResetArgument("a", "level 5", None),
        ResetArgument("a.n", "level 4", None),
        ResetArgument("a.n.n", "level 3", None),
        ResetArgument("a.n.n.n", "level 2", None),
    ]


def test_const_and_oneof_are_not_read_as_values():
    schema = {
        "properties": {
            "fixed": {"const": "only", "description": "c"},
            "choice": {"oneOf": [{"const": "a"}, {"const": "b"}]},
        }
    }
    assert reset_arguments(schema) == [
        ResetArgument("fixed", "c", None),
        ResetArgument("choice", None, None),
    ]


def test_non_string_values_render_as_json():
    schema = {"properties": {"level": {"enum": [1, True, None, "two"]}}}
    brief = reset_arguments_brief(schema)
    assert brief is not None
    assert "- level\n  Values: 1 | true | null | two\n" in brief


@pytest.mark.parametrize(
    "schema",
    [
        None,
        {},
        {"type": "object", "properties": {}},
        {"properties": {"seed": {"type": "integer"}, "episode_id": {"type": "string"}}},
        {"properties": "not an object"},
    ],
)
def test_no_arguments_gives_no_brief(schema):
    assert reset_arguments_brief(schema) is None
