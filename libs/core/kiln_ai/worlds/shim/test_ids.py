from __future__ import annotations

import sys
import uuid

import pytest

from .errors import WorldBug
from .ids import Ids, instance_seed

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="the worlds runtime needs Python 3.12+"
)


def test_same_seed_same_stream():
    first = Ids(instance_seed("company-v1", 7))
    second = Ids(instance_seed("company-v1", 7))
    assert [first.uuid() for _ in range(5)] == [second.uuid() for _ in range(5)]
    assert first.random.random() == second.random.random()


def test_int_bytes_none_seeds_distinct():
    seeds = {
        instance_seed("company-v1", None),
        instance_seed("company-v1", 0),
        instance_seed("company-v1", 7),
        instance_seed("company-v1", b"7"),
    }
    assert len(seeds) == 4


@pytest.mark.parametrize("seed", [-1, 1 << 64, 2**70])
def test_out_of_range_int_refused(seed):
    """Both ends stay inside the SeahavenError hierarchy: an `except WorldBug` around
    `world.instance(...)` must not have to also catch OverflowError."""
    with pytest.raises(WorldBug, match="eight bytes"):
        instance_seed("company-v1", seed)
    assert instance_seed("company-v1", (1 << 64) - 1)


def test_unsupported_seed_type_refused():
    with pytest.raises(WorldBug, match="bytes"):
        instance_seed("company-v1", "seven")


def test_fixture_source_changes_stream():
    """Two fixtures with the same caller seed must not mint the same ids."""
    assert instance_seed("company-v1", 7) != instance_seed("company-v2", 7)
    assert (
        Ids(instance_seed("company-v1", 7)).uuid()
        != Ids(instance_seed("company-v2", 7)).uuid()
    )


def test_uuid_version_and_variant_bits():
    ids = Ids(instance_seed("w", None))
    minted = [ids.uuid() for _ in range(20)]
    assert len(set(minted)) == 20
    for text in minted:
        value = uuid.UUID(text)
        assert value.version == 4
        assert value.variant == uuid.RFC_4122
        assert text == text.lower() and str(value) == text
