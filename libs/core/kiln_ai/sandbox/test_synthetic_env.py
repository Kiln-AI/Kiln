"""Tests for the stdlib-only synthetic-instance handoff into sandbox children."""

import os
import sys

import pytest

from kiln_ai.sandbox.synthetic_env import (
    ENV_FIXTURE_DATA_PATH,
    ENV_FROZEN_TIME,
    ENV_INSTANCE_ID,
    ENV_INSTANCE_PATH,
    ENV_WORLD_LIB_PATH,
    apply_synthetic_instance,
    synthetic_instance_from_env,
)

ALL_ENV = [
    ENV_INSTANCE_ID,
    ENV_INSTANCE_PATH,
    ENV_FIXTURE_DATA_PATH,
    ENV_FROZEN_TIME,
    ENV_WORLD_LIB_PATH,
    "KILN_SYNTHETIC_WORLD_ID",
    "KILN_SYNTHETIC_FIXTURE_ID",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ALL_ENV:
        monkeypatch.delenv(name, raising=False)
    original_path = list(sys.path)
    yield
    sys.path[:] = original_path


def test_none_is_noop():
    apply_synthetic_instance(None)
    assert synthetic_instance_from_env() is None
    assert ENV_INSTANCE_ID not in os.environ


def test_exports_env_and_lib_path(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    apply_synthetic_instance(
        {
            "instance_id": "inst_1",
            "world_id": "w",
            "fixture_id": "f",
            "path": "/inst",
            "fixture_data_path": "/fixture",
            "frozen_time": "2026-07-14T00:00:00+00:00",
            "world_lib_path": str(lib),
            "framework_content_hash": "eng1",
            "unchanged": False,
        }
    )
    assert os.environ[ENV_INSTANCE_ID] == "inst_1"
    assert os.environ[ENV_INSTANCE_PATH] == "/inst"
    assert os.environ[ENV_FROZEN_TIME] == "2026-07-14T00:00:00+00:00"
    assert sys.path[0] == str(lib)
    seen = synthetic_instance_from_env()
    assert seen is not None
    assert seen["instance_id"] == "inst_1"
    assert seen["world_lib_path"] == str(lib)


def test_none_values_are_not_exported_as_strings():
    apply_synthetic_instance(
        {
            "instance_id": "inst_2",
            "world_id": "w",
            "fixture_id": "f",
            "path": "/inst",
            "fixture_data_path": "/fixture",
            "frozen_time": None,
            "world_lib_path": None,
        }
    )
    assert ENV_FROZEN_TIME not in os.environ
    assert ENV_WORLD_LIB_PATH not in os.environ


def test_missing_lib_dir_is_not_added_to_path(tmp_path):
    apply_synthetic_instance(
        {
            "instance_id": "inst_3",
            "world_id": "w",
            "fixture_id": "f",
            "path": "/inst",
            "fixture_data_path": "/fixture",
            "world_lib_path": str(tmp_path / "missing"),
        }
    )
    assert str(tmp_path / "missing") not in sys.path
