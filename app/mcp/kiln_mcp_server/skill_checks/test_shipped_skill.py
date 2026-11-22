"""Checks of the skill tree as shipped in this package."""

import pytest

from kiln_mcp_server.api_tool.tool import DEFAULT_BODY_LIMIT
from kiln_mcp_server.skill_checks.tree_check import (
    TREE_RULES,
    check_tree,
    default_root,
    tree_paths,
)
from kiln_mcp_server.skill_files import API_CATALOGUE_INDEX_PATH, get_index, read_file

# Rules whose problems do not fail the shipped-tree test yet.
PENDING_RULES: set[str] = set()

# Files allowed over the size limit, each with its reason.
OVER_BODY_LIMIT_ALLOWED: dict[str, str] = {}


@pytest.fixture(scope="module")
def shipped_problems():
    return check_tree(default_root())


def test_pending_rules_are_tree_rules():
    assert PENDING_RULES <= set(TREE_RULES)


def test_the_shipped_tree_passes_every_check(shipped_problems):
    failing = [p for p in shipped_problems if p.rule not in PENDING_RULES]
    assert failing == []


def test_the_check_reads_the_served_files():
    assert tree_paths(default_root()) == frozenset(get_index().files)


def test_the_catalogue_index_exists():
    assert (default_root() / API_CATALOGUE_INDEX_PATH).is_file()
    assert API_CATALOGUE_INDEX_PATH in get_index().files


def test_no_file_over_body_limit():
    index = get_index()
    sizes = {key: len(read_file(key, index)) for key in index.files}
    over = {
        key: size
        for key, size in sizes.items()
        if size > DEFAULT_BODY_LIMIT and key not in OVER_BODY_LIMIT_ALLOWED
    }
    assert over == {}
