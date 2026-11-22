import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from kiln_mcp_server.skill_checks.api_reference import (
    CATALOGUE_SUFFIX,
    INDEX_NAME,
    ApiReferenceError,
    diff_folder,
    endpoint_doc_name,
    render,
)
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
        and not path.name.endswith(CATALOGUE_SUFFIX)
        and not path.name.startswith(".")
    }
    assert committed == allowed
    assert not committed & blocked


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
