"""Tests for the stdlib-only synthetic-instance handoff into sandbox children."""

import json
import os
import sys

import pytest

from kiln_ai.sandbox.synthetic_env import (
    ENV_CONFIG,
    ENV_CONNECTION,
    ENV_ENDPOINT,
    ENV_INSTANCE_ID,
    ENV_INSTANCE_PATH,
    ENV_METADATA,
    ENV_SOURCE_PATH,
    ENV_WORLD_LIB_PATH,
    apply_synthetic_instance,
    metadata_env_name,
    synthetic_instance_from_env,
)

ALL_ENV = [
    ENV_INSTANCE_ID,
    ENV_INSTANCE_PATH,
    ENV_ENDPOINT,
    ENV_SOURCE_PATH,
    ENV_WORLD_LIB_PATH,
    ENV_CONFIG,
    ENV_METADATA,
    ENV_CONNECTION,
    "KILN_SYNTHETIC_WORLD_ID",
    "KILN_SYNTHETIC_FROZEN_TIME",
    "KILN_SYNTHETIC_FIXTURE_ID",
    "KILN_SYNTHETIC_PLAN",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ALL_ENV:
        monkeypatch.delenv(name, raising=False)
    original_path = list(sys.path)
    yield
    sys.path[:] = original_path


def _instance(**overrides):
    base = {
        "instance_id": "inst_1",
        "world_id": "w",
        "config": {"fixture_id": "alpha"},
        "path": "/inst",
        "endpoint": None,
        "connection": None,
        "source_path": "/fixture",
        "world_lib_path": None,
        "metadata": {"fixture_id": "alpha", "frozen_time": "2026-07-14T00:00:00+00:00"},
        "content_version": "eng1",
        "unchanged": False,
    }
    base.update(overrides)
    return base


def test_none_is_noop():
    apply_synthetic_instance(None)
    assert synthetic_instance_from_env() is None
    assert ENV_INSTANCE_ID not in os.environ


def test_exports_env_json_and_metadata_scalars(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    apply_synthetic_instance(
        _instance(
            world_lib_path=str(lib),
            metadata={
                "fixture_id": "alpha",
                "frozen_time": "2026-07-14T00:00:00+00:00",
                "plan": "pro",
                "nested": {"x": 1},
            },
        )
    )
    assert os.environ[ENV_INSTANCE_ID] == "inst_1"
    assert os.environ[ENV_INSTANCE_PATH] == "/inst"
    assert os.environ[ENV_SOURCE_PATH] == "/fixture"
    assert json.loads(os.environ[ENV_CONFIG]) == {"fixture_id": "alpha"}
    assert json.loads(os.environ[ENV_METADATA])["plan"] == "pro"
    assert os.environ["KILN_SYNTHETIC_FROZEN_TIME"] == "2026-07-14T00:00:00+00:00"
    assert os.environ["KILN_SYNTHETIC_FIXTURE_ID"] == "alpha"
    assert os.environ["KILN_SYNTHETIC_PLAN"] == "pro"
    assert "KILN_SYNTHETIC_NESTED" not in os.environ
    assert sys.path[0] == str(lib)
    seen = synthetic_instance_from_env()
    assert seen is not None
    assert seen["instance_id"] == "inst_1"
    assert seen["config"] == {"fixture_id": "alpha"}
    assert seen["metadata"]["frozen_time"] == "2026-07-14T00:00:00+00:00"


def test_none_values_are_not_exported_as_strings():
    apply_synthetic_instance(_instance(endpoint=None, world_lib_path=None, metadata={}))
    assert ENV_ENDPOINT not in os.environ
    assert ENV_WORLD_LIB_PATH not in os.environ
    assert "KILN_SYNTHETIC_FROZEN_TIME" not in os.environ


def test_endpoint_only_instance():
    connection = {
        "transport": "http",
        "url": "http://host:9000/inst_1",
        "headers": {"Authorization": "Bearer s3cret"},
        "command": None,
        "args": [],
        "env": {},
    }
    apply_synthetic_instance(
        _instance(
            path=None,
            source_path=None,
            endpoint="http://host:9000/inst_1",
            connection=connection,
        )
    )
    assert os.environ[ENV_ENDPOINT] == "http://host:9000/inst_1"
    assert ENV_INSTANCE_PATH not in os.environ
    assert json.loads(os.environ[ENV_CONNECTION]) == connection
    seen = synthetic_instance_from_env()
    assert seen is not None and seen["connection"] == connection


def test_no_connection_is_not_exported():
    apply_synthetic_instance(_instance())
    assert ENV_CONNECTION not in os.environ
    seen = synthetic_instance_from_env()
    assert seen is not None and seen["connection"] is None


def test_metadata_key_cannot_shadow_reserved_names():
    apply_synthetic_instance(
        _instance(metadata={"instance_id": "evil", "config": "evil"})
    )
    assert os.environ[ENV_INSTANCE_ID] == "inst_1"
    assert json.loads(os.environ[ENV_CONFIG]) == {"fixture_id": "alpha"}


def test_missing_lib_dir_is_not_added_to_path(tmp_path):
    apply_synthetic_instance(_instance(world_lib_path=str(tmp_path / "missing")))
    assert str(tmp_path / "missing") not in sys.path


@pytest.mark.parametrize(
    "key, name",
    [
        ("frozen_time", "KILN_SYNTHETIC_FROZEN_TIME"),
        ("Plan Tier", "KILN_SYNTHETIC_PLAN_TIER"),
        ("x-y", "KILN_SYNTHETIC_X_Y"),
    ],
)
def test_metadata_env_name(key, name):
    assert metadata_env_name(key) == name
