import json
import os
import re
import sys
from collections import defaultdict

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from kiln_mcp_server.skill_checks.api_reference import (
    CATALOGUE_SUFFIX,
    HAND_WRITTEN_NAMES,
    INDEX_NAME,
    TARGET,
    ApiReferenceError,
    diff_folder,
    endpoint_doc_name,
    render,
)
from kiln_mcp_server.skill_files import get_index, read_file
from kiln_server.utils.agent_checks import is_mcp_denied

from app.desktop import skill_api_reference
from app.desktop.desktop_server import make_app
from app.desktop.skill_api_reference import FIX_COMMAND, SKIPPED, current_spec, main

needs_generator_python = pytest.mark.skipif(
    sys.version_info < (3, 13), reason="the generator needs Python 3.13"
)


@pytest.mark.slow
@needs_generator_python
def test_the_committed_api_reference_is_current():
    differences = diff_folder(
        render(current_spec()), skill_api_reference.default_target()
    )
    assert differences == [], f"Run `{FIX_COMMAND}`"


def test_committed_docs_match_the_block_list():
    allowed: set[str] = set()
    blocked: set[str] = set()
    for route in make_app().routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            names = {endpoint_doc_name(method, route.path) for method in route.methods}
            (blocked if is_mcp_denied(route.openapi_extra) else allowed).update(names)

    committed = {
        path.name
        for path in skill_api_reference.default_target().iterdir()
        if path.name != INDEX_NAME
        and path.name not in HAND_WRITTEN_NAMES
        and not path.name.endswith(CATALOGUE_SUFFIX)
        and not path.name.startswith(".")
    }
    assert committed == allowed
    assert not committed & blocked


_PATH_CHAR = r"A-Za-z0-9_\-/{}"
_PARAM = r"(?:\{[^}/\s]*\}|[^/\s`'\"()|]+)"


def _path_pattern(template: str) -> re.Pattern[str]:
    """Matches `template` as written in a skill file: a `{param}` stands for
    any `{...}` placeholder or one concrete path segment."""
    parts = re.split(r"\{[^}]+\}", template)
    body = _PARAM.join(re.escape(part) for part in parts)
    return re.compile(rf"(?<![{_PATH_CHAR}]){body}(?![{_PATH_CHAR}])")


def _blocked_endpoint_hits(
    text: str, blocked: dict[str, set[str]], allowed: dict[str, set[str]]
) -> list[str]:
    """`METHOD path` of each blocked endpoint that a line of `text` names. A
    path that also has an allowed method counts only when a blocked method
    is on the same line."""
    hits = []
    for line in text.split("\n"):
        for template, methods in blocked.items():
            if not _path_pattern(template).search(line):
                continue
            if not allowed.get(template):
                hits.extend(f"{m} {template}" for m in sorted(methods))
                continue
            hits.extend(
                f"{m} {template}"
                for m in sorted(methods)
                if re.search(rf"\b{m}\b", line)
            )
    return hits


def _routes_by_policy() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    blocked: dict[str, set[str]] = defaultdict(set)
    allowed: dict[str, set[str]] = defaultdict(set)
    for route in make_app().routes:
        if isinstance(route, APIRoute):
            target = blocked if is_mcp_denied(route.openapi_extra) else allowed
            target[route.path].update(route.methods)
    return blocked, allowed


def test_no_skill_file_names_a_blocked_endpoint():
    blocked, allowed = _routes_by_policy()
    assert blocked
    index = get_index()
    hits = {
        key: found
        for key in index.files
        if not key.startswith(TARGET + "/")
        and (found := _blocked_endpoint_hits(read_file(key, index), blocked, allowed))
    }
    assert hits == {}


BLOCKED = {"/api/provider/connect_api_key": {"POST"}, "/api/settings": {"POST"}}
ALLOWED = {"/api/settings": {"GET"}}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "Call `POST /api/provider/connect_api_key`.",
            ["POST /api/provider/connect_api_key"],
        ),
        ("/api/provider/connect_api_key_v2", []),
        ("Read `GET /api/settings` first.", []),
        ("`POST /api/settings` writes it.", ["POST /api/settings"]),
        ("`GET /api/settings/available_providers`", []),
    ],
)
def test_the_blocked_endpoint_matcher(line, expected):
    assert _blocked_endpoint_hits(line, BLOCKED, ALLOWED) == expected


def test_a_path_parameter_matches_a_placeholder_or_a_segment():
    pattern = _path_pattern("/api/projects/{project_id}/open")
    assert pattern.search("`/api/projects/{project_id}/open`")
    assert pattern.search("/api/projects/123/open")
    assert not pattern.search("/api/projects/123/open_logs")
    assert not pattern.search("/api/projects/a/b/open")


def test_current_spec_skips_the_remote_model_list(monkeypatch):
    monkeypatch.delenv("KILN_SKIP_REMOTE_MODEL_LIST", raising=False)
    seen: list[str | None] = []

    def fake_make_app() -> FastAPI:
        seen.append(os.environ.get("KILN_SKIP_REMOTE_MODEL_LIST"))
        return FastAPI(title="Kiln")

    monkeypatch.setattr(skill_api_reference, "make_app", fake_make_app)
    assert current_spec()["info"]["title"] == "Kiln"
    assert seen == ["true"]


@pytest.fixture
def spec_file(tmp_path):
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps({"openapi": "3.1.0", "paths": {}}))
    return path


def fake_render(files: dict[str, bytes]):
    def renderer(spec: dict) -> dict[str, bytes]:
        assert spec == {"openapi": "3.1.0", "paths": {}}
        return files

    return renderer


@needs_generator_python
def test_generate_writes_the_folder(tmp_path, spec_file, capsys):
    target = tmp_path / "api_docs"
    code = main(
        ["generate", "--spec", str(spec_file)],
        target=target,
        renderer=fake_render({"a.md": b"a"}),
    )
    assert code == 0
    assert [p.name for p in target.iterdir()] == ["a.md"]
    assert "Wrote 1 files" in capsys.readouterr().out


@needs_generator_python
def test_check_passes_on_a_current_folder(tmp_path, spec_file, capsys):
    target = tmp_path / "api_docs"
    target.mkdir()
    (target / "a.md").write_bytes(b"a")
    code = main(
        ["check", "--spec", str(spec_file)],
        target=target,
        renderer=fake_render({"a.md": b"a"}),
    )
    assert code == 0
    assert capsys.readouterr().out == "API reference up to date\n"


@needs_generator_python
def test_check_reports_a_stale_folder(tmp_path, spec_file, capsys):
    target = tmp_path / "api_docs"
    target.mkdir()
    (target / "a.md").write_bytes(b"old")
    code = main(
        ["check", "--spec", str(spec_file)],
        target=target,
        renderer=fake_render({"a.md": b"new", "b.md": b"b"}),
    )
    assert code == 1
    assert capsys.readouterr().out.splitlines() == [
        "The API reference is not current:",
        "  changed a.md",
        "  added b.md",
        f"Run `{FIX_COMMAND}` and commit the folder.",
    ]


@needs_generator_python
def test_a_generator_error_exits_1(tmp_path, spec_file, capsys):
    def failing(spec: dict) -> dict[str, bytes]:
        raise ApiReferenceError("boom")

    code = main(["check", "--spec", str(spec_file)], target=tmp_path, renderer=failing)
    assert code == 1
    assert capsys.readouterr().err == "Cannot generate the API reference: boom\n"


@needs_generator_python
def test_a_missing_spec_file_is_a_usage_error(tmp_path, capsys):
    code = main(["check", "--spec", str(tmp_path / "missing.json")], target=tmp_path)
    assert code == 2
    assert "No such file" in capsys.readouterr().err


@needs_generator_python
@pytest.mark.parametrize("content", [b"{not json", b"\xff\xfe", b"[1, 2]"])
def test_a_malformed_spec_file_is_a_usage_error(tmp_path, capsys, content):
    spec = tmp_path / "openapi.json"
    spec.write_bytes(content)
    assert main(["check", "--spec", str(spec)], target=tmp_path) == 2
    assert str(spec) in capsys.readouterr().err


def test_check_below_3_13_skips(monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", (3, 12, 0))
    assert main(["check"]) == 0
    assert capsys.readouterr().out == SKIPPED


def test_generate_below_3_13_is_a_usage_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", (3, 12, 0))
    assert main(["generate"]) == 2
    assert "needs Python 3.13" in capsys.readouterr().err
