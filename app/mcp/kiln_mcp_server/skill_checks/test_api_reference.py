import copy
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from kiln_mcp_server.skill_checks.api_reference import (
    HAND_WRITTEN_NAMES,
    ApiReferenceError,
    catalogue_index,
    diff_folder,
    drop_blocked,
    endpoint_doc_name,
    normalise,
    render,
    run_generator,
    write_folder,
)
from kiln_mcp_server.skill_files import (
    API_CATALOGUE_INDEX_NAME,
    API_CATALOGUE_INDEX_PATH,
    API_DOCS_FOLDER,
    API_RULES_PATH,
)

DENY = {"x-mcp-policy": {"permission": "deny"}}


def operation(tag: str | None = "Projects", **extra) -> dict:
    result: dict = {
        "summary": "An operation",
        "responses": {"200": {"description": "OK"}},
    }
    if tag is not None:
        result["tags"] = [tag]
    return {**result, **extra}


def make_spec() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Kiln", "version": "1.2.3"},
        "tags": [
            {"name": "Projects", "description": "Create and read\nprojects."},
            {"name": "Runs", "description": "Run | view tasks."},
        ],
        "paths": {
            "/api/projects": {"get": operation(), "post": operation()},
            "/api/projects/{project_id}": {
                "get": operation(),
                "delete": operation(**DENY),
            },
            "/api/secret": {"post": operation(**DENY)},
            "/api/runs": {"get": operation("Runs")},
        },
    }


def test_drop_blocked_removes_operations_and_empty_paths():
    spec = make_spec()
    original = copy.deepcopy(spec)
    result = drop_blocked(spec)
    assert set(result["paths"]) == {
        "/api/projects",
        "/api/projects/{project_id}",
        "/api/runs",
    }
    assert set(result["paths"]["/api/projects/{project_id}"]) == {"get"}
    assert spec == original


def test_a_path_item_key_that_is_not_an_operation_is_kept():
    spec = make_spec()
    spec["paths"]["/api/secret"]["parameters"] = []
    spec["paths"]["/api/runs"]["parameters"] = []
    result = drop_blocked(spec)
    assert "/api/secret" not in result["paths"]
    assert result["paths"]["/api/runs"]["parameters"] == []


@pytest.mark.parametrize("method", ["put", "head", "options", "trace"])
def test_other_method_stops(method):
    spec = make_spec()
    spec["paths"]["/api/runs"][method] = operation("Runs")
    with pytest.raises(ApiReferenceError, match=f"{method.upper()} /api/runs"):
        drop_blocked(spec)


def test_a_blocked_operation_of_another_method_is_dropped():
    spec = make_spec()
    spec["paths"]["/api/runs"]["put"] = operation("Runs", **DENY)
    assert set(drop_blocked(spec)["paths"]["/api/runs"]) == {"get"}


def test_version_is_normalised():
    spec = make_spec()
    result = normalise(spec)
    assert result["info"] == {"title": "Kiln", "version": "0.0.0"}
    assert spec["info"]["version"] == "1.2.3"


@pytest.mark.parametrize(
    "method, path, name",
    [
        ("GET", "/api/projects", "get_api_projects.md"),
        (
            "post",
            "/api/projects/{project_id}/Tasks",
            "post_api_projects_project_id_tasks.md",
        ),
        ("DELETE", "/", "delete.md"),
    ],
)
def test_endpoint_doc_name(method, path, name):
    assert endpoint_doc_name(method, path) == name


def catalogue(tag: str, rows: int) -> bytes:
    lines = [
        f"# {tag} API",
        "",
        "Description.",
        "",
        "|Endpoint|Method|Name|Description|Details File|",
        "|-|-|-|-|-|",
    ]
    lines += [f"|`/api/x{i}`|GET|X||get_api_x{i}.md|" for i in range(rows)]
    return ("\n".join(lines) + "\n").encode()


def test_catalogue_index_rows():
    spec = make_spec()
    spec["paths"]["/api/other"] = {"get": operation(None)}
    files = {
        "runs_api_list.md": catalogue("Runs", 1),
        "other_api_list.md": catalogue("Other", 1),
        "projects_api_list.md": catalogue("Projects", 3),
        "get_api_projects.md": b"# doc\n",
    }
    text = catalogue_index(spec, files).decode()
    table = [line for line in text.split("\n") if line.startswith("|")]
    assert table == [
        "| Catalogue | Area | Endpoints | What it covers |",
        "|---|---|---|---|",
        f"| `{API_DOCS_FOLDER}/projects_api_list.md` | Projects | 3 | Create and read projects. |",
        f"| `{API_DOCS_FOLDER}/runs_api_list.md` | Runs | 1 | Run \\| view tasks. |",
        f"| `{API_DOCS_FOLDER}/other_api_list.md` | Other | 1 |  |",
    ]
    assert text.startswith("# Kiln API catalogues\n")
    assert f"Read an endpoint doc at `{API_DOCS_FOLDER}/<file name>`." in text
    assert text.endswith("|\n")
    assert API_CATALOGUE_INDEX_PATH == "references/knowledge/api_docs/api_index.md"


def test_write_folder_replaces_whole_folder(tmp_path):
    target = tmp_path / "skill" / "api_docs"
    target.mkdir(parents=True)
    (target / "old.md").write_bytes(b"old")
    (target / "keep.md").write_bytes(b"before")
    write_folder({"keep.md": b"after", "new.md": b"new"}, target)
    assert sorted(p.name for p in target.iterdir()) == ["keep.md", "new.md"]
    assert (target / "keep.md").read_bytes() == b"after"
    assert [p.name for p in target.parent.iterdir()] == ["api_docs"]
    assert stat.S_IMODE(target.stat().st_mode) == stat.S_IMODE(
        target.parent.stat().st_mode
    )


def test_write_folder_clears_a_leftover_staging_folder(tmp_path):
    target = tmp_path / "api_docs"
    leftover = tmp_path / ".api_docs_staging"
    leftover.mkdir()
    (leftover / "stale.md").write_bytes(b"stale")
    write_folder({"x.md": b"x"}, target)
    assert [p.name for p in target.iterdir()] == ["x.md"]
    assert not leftover.exists()


def test_write_folder_creates_a_missing_folder(tmp_path):
    target = tmp_path / "a" / "api_docs"
    write_folder({"x.md": b"x"}, target)
    assert (target / "x.md").read_bytes() == b"x"


def test_the_api_rules_are_the_hand_written_file_of_the_folder():
    assert API_RULES_PATH == "references/knowledge/api_docs/calling_the_kiln_api.md"
    assert HAND_WRITTEN_NAMES == {"calling_the_kiln_api.md"}


def test_write_folder_keeps_the_hand_written_files(tmp_path):
    target = tmp_path / "api_docs"
    write_folder({"old.md": b"old"}, target)
    (target / "calling_the_kiln_api.md").write_bytes(b"rules")
    write_folder({"new.md": b"new"}, target)
    assert sorted(p.name for p in target.iterdir()) == [
        "calling_the_kiln_api.md",
        "new.md",
    ]
    assert (target / "calling_the_kiln_api.md").read_bytes() == b"rules"


def test_diff_folder_leaves_out_the_hand_written_files(tmp_path):
    target = tmp_path / "api_docs"
    write_folder({"same.md": b"s"}, target)
    (target / "calling_the_kiln_api.md").write_bytes(b"rules")
    assert diff_folder({"same.md": b"s"}, target) == []


def test_diff_folder_reports_added_removed_changed(tmp_path):
    target = tmp_path / "api_docs"
    write_folder({"same.md": b"s", "changed.md": b"old", "removed.md": b"r"}, target)
    (target / ".DS_Store").write_bytes(b"finder")
    files = {"same.md": b"s", "changed.md": b"new", "added.md": b"a"}
    assert diff_folder(files, target) == [
        "added added.md",
        "changed changed.md",
        "removed removed.md",
    ]
    assert diff_folder(files, tmp_path / "missing") == [
        "added added.md",
        "added changed.md",
        "added same.md",
    ]


FAKE_GENERATOR = """
import argparse, json, pathlib, sys
parser = argparse.ArgumentParser()
parser.add_argument("--spec")
parser.add_argument("--output")
args = parser.parse_args()
spec = json.loads(pathlib.Path(args.spec).read_text(encoding="utf-8"))
reference = pathlib.Path(args.output) / "2026-01-01_000000" / "reference"
reference.mkdir(parents=True)
(reference.parent / "SKILL.md").write_text("generator skill")
docs = 0
for path, item in spec["paths"].items():
    for method in item:
        name = method + path.replace("/", "_").replace("{", "").replace("}", "")
        (reference / (name + ".md")).write_bytes("doc\\r\\nline\\n".encode())
        docs += 1
(reference / "projects_api_list.md").write_bytes(b"# Projects API\\n\\n|a|\\n|-|\\n|b|\\n")
{extra}
"""


def fake_generator(tmp_path: Path, extra: str = "") -> tuple[str, ...]:
    script = tmp_path / "fake_generator.py"
    script.write_text(FAKE_GENERATOR.replace("{extra}", textwrap.dedent(extra)))
    return (sys.executable, str(script))


def test_newlines_are_normalised_and_skill_md_ignored(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = drop_blocked(make_spec())
    files = run_generator(spec, workdir, command=fake_generator(tmp_path))
    assert sorted(files) == [
        "get_api_projects.md",
        "get_api_projects_project_id.md",
        "get_api_runs.md",
        "post_api_projects.md",
        "projects_api_list.md",
    ]
    assert files["get_api_runs.md"] == b"doc\nline\n"


def test_collision_warning_stops(tmp_path):
    command = fake_generator(
        tmp_path,
        'sys.stderr.write("Warning: filename collision for get_/x, using get_x_2.md\\n")',
    )
    with pytest.raises(ApiReferenceError, match="get the same file name"):
        run_generator(drop_blocked(make_spec()), tmp_path, command=command)


def test_tag_collision_warning_stops(tmp_path):
    command = fake_generator(
        tmp_path,
        "sys.stderr.write(\"Warning: tag filename collision for 'A/B', using ab_api_list_2.md\\n\")",
    )
    with pytest.raises(ApiReferenceError, match="tag filename collision"):
        run_generator(drop_blocked(make_spec()), tmp_path, command=command)


def test_generator_failure_stops(tmp_path):
    command = fake_generator(tmp_path, 'sys.stderr.write("boom\\n"); sys.exit(3)')
    with pytest.raises(ApiReferenceError, match="exited with 3:\nboom"):
        run_generator(drop_blocked(make_spec()), tmp_path, command=command)


def test_endpoint_count_mismatch_stops(tmp_path):
    command = fake_generator(tmp_path, '(reference / "extra.md").write_text("x")')
    with pytest.raises(ApiReferenceError, match="5 endpoint docs for 4 operations"):
        run_generator(drop_blocked(make_spec()), tmp_path, command=command)


def test_no_output_folder_stops(tmp_path):
    script = tmp_path / "quiet.py"
    script.write_text("pass\n")
    with pytest.raises(ApiReferenceError, match="one output folder"):
        run_generator(make_spec(), tmp_path, command=(sys.executable, str(script)))


def test_no_reference_folder_stops(tmp_path):
    command = fake_generator(tmp_path, "import shutil; shutil.rmtree(reference)")
    with pytest.raises(ApiReferenceError, match="no reference folder"):
        run_generator(drop_blocked(make_spec()), tmp_path, command=command)


def test_render_adds_the_index_and_drops_blocked_operations(tmp_path):
    files = render(make_spec(), command=fake_generator(tmp_path))
    assert API_CATALOGUE_INDEX_NAME in files
    assert "delete_api_projects_project_id.md" not in files
    assert list(files) == sorted(files)
    assert b"| Projects | 1 |" in files[API_CATALOGUE_INDEX_NAME]


@pytest.mark.skipif(sys.version_info < (3, 13), reason="the generator needs 3.13")
def test_render_with_the_real_generator():
    spec = make_spec()
    spec["paths"]["/api/projects/{project_id}"]["patch"] = operation()
    first = render(spec)
    assert render(spec) == first
    assert set(first) == {
        API_CATALOGUE_INDEX_NAME,
        "projects_api_list.md",
        "runs_api_list.md",
        "get_api_projects.md",
        "post_api_projects.md",
        "get_api_projects_project_id.md",
        "patch_api_projects_project_id.md",
        "get_api_runs.md",
    }
    assert b"\r" not in b"".join(first.values())
    assert b"| Projects | 4 |" in first[API_CATALOGUE_INDEX_NAME]
