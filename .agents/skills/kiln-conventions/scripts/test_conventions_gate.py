import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

GATE_PATH = Path(__file__).resolve().parent / "conventions_gate.py"
_spec = importlib.util.spec_from_file_location("conventions_gate", GATE_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
sys.modules["conventions_gate"] = gate
_spec.loader.exec_module(gate)

ALL_CHECKS = [check.rule for check in gate.CHECKS]

BASE_CONFIG = {
    "skip_globs": ["**/test_*.py", "**/*.test.ts", "**/__tests__/**", "gen/**"],
    "checks": {
        **{rule: {} for rule in ALL_CHECKS},
        "core-config-shared": {"paths": ["libs/core/kiln_ai/**"]},
        "lib-imports-routes": {"paths": ["web/src/lib/**"]},
        "module-level-subscribe": {"paths": ["web/src/lib/**"]},
    },
    "env_access_allowed": ["pkg/config.py", "entry/**"],
    "module_level_call_ignore": [r"\.include_router\("],
    "module_level_construct_patterns": [r"\bmake_app\(", r"Registry\("],
}


def make_config(**overrides) -> "gate.Config":
    return gate.parse_config({**BASE_CONFIG, **overrides}, "test")


def rules_hit(path: str, text: str, cfg=None) -> list[str]:
    result = gate.run_checks([gate.Line(path, 1, text)], cfg or make_config(), [])
    return [hit.rule for hit in result.hits]


def test_parse_unified_diff_multi_hunk():
    diff = (
        "diff --git a/a.py b/a.py\n"
        "index 1..2 100644\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,0 +2,2 @@\n"
        "+first\n"
        "+second\n"
        "@@ -10 +12 @@\n"
        "-old\n"
        "+third\n"
    )
    assert gate.parse_unified_diff(diff) == [
        gate.Line("a.py", 2, "first"),
        gate.Line("a.py", 3, "second"),
        gate.Line("a.py", 12, "third"),
    ]


def test_parse_unified_diff_new_and_renamed_files():
    diff = (
        "diff --git a/new.py b/new.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/new.py\n"
        "@@ -0,0 +1 @@\n"
        "+x = 1\n"
        "diff --git a/old.py b/moved.py\n"
        "similarity index 90%\n"
        "rename from old.py\n"
        "rename to moved.py\n"
        "--- a/old.py\n"
        "+++ b/moved.py\n"
        "@@ -3 +3 @@\n"
        "-y = 1\n"
        "+y = 2\n"
    )
    assert gate.parse_unified_diff(diff) == [
        gate.Line("new.py", 1, "x = 1"),
        gate.Line("moved.py", 3, "y = 2"),
    ]


def test_parse_unified_diff_skips_markers_and_deletions():
    diff = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1 +1 @@\n"
        "-gone\n"
        "\\ No newline at end of file\n"
        "+kept\n"
        "\\ No newline at end of file\n"
        "diff --git a/b.py b/b.py\n"
        "deleted file mode 100644\n"
        "--- a/b.py\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-removed\n"
    )
    assert gate.parse_unified_diff(diff) == [gate.Line("a.py", 1, "kept")]


def test_parse_unified_diff_added_line_that_looks_like_a_header():
    diff = (
        "diff --git a/a.ts b/a.ts\n"
        "--- a/a.ts\n"
        "+++ b/a.ts\n"
        "@@ -0,0 +1,2 @@\n"
        "+++ count\n"
        "+--- x\n"
    )
    assert gate.parse_unified_diff(diff) == [
        gate.Line("a.ts", 1, "++ count"),
        gate.Line("a.ts", 2, "--- x"),
    ]


def test_diff_path_handles_quoted_and_spaced_names():
    assert gate._diff_path('"b/a \\"q\\".py"') == 'a "q".py'
    assert gate._diff_path("b/a b.py\t") == "a b.py"


@pytest.mark.parametrize(
    "text, lang, comment",
    [
        ("x = 1  # set x", "py", "set x"),
        ('x = "a # b"', "py", None),
        ("x = 'a # b'  # real", "py", "real"),
        ('x = """a # b"""  # real', "py", "real"),
        ('x = """starts a docstring # not a comment', "py", None),
        ("x = 1", "py", None),
        ("const a = 1 // note", "ts", "note"),
        ('const url = "https://x.y" // note', "ts", "note"),
        ("href=https://x.y/z", "svelte", None),
        ("const s = 'a // b'", "ts", None),
        ("const t = `a // b`", "ts", None),
        ("const a = /* inline */ 1", "ts", "inline"),
        ("   * JSDoc continuation", "ts", "JSDoc continuation"),
        ("   * last line */", "ts", "last line"),
        ("<div><!-- markup note --></div>", "svelte", "markup note"),
        ("/* opens a block", "ts", "opens a block"),
        ("<!-- opens markup", "svelte", "opens markup"),
        ("const a = 1", "ts", None),
    ],
)
def test_extract_comment(text, lang, comment):
    assert gate.extract_comment(text, lang) == comment


def test_split_code_comment_keeps_code_around_inline_block():
    assert gate.split_code_comment("a /* b */ c", "ts") == ("a  c", "b")


@pytest.mark.parametrize(
    "comment",
    [
        "this is no longer cached",
        "previously we stored a dict",
        "previously, the cache was global",
        "this used to retry",
        "they never used to make calls",
        "formerly the default",
        "the Optional is vestigial",
        "bumped from 8",
        "switched to httpx",
        "changed from 8 to 16",
        "the field was renamed",
        "after the refactor this is safe",
        "matches the old behavior",
        "added in this PR",
        "as of this change",
        "Phase 2 maps these to 409",
        "see functional spec 5.2",
        "see functional_spec",
        "per architecture §7",
        "(P2) follow-up",
    ],
)
def test_history_patterns_hit(comment):
    assert gate.has_history_phrase(comment)


@pytest.mark.parametrize(
    "comment",
    [
        "the key is used to sign requests",
        "Used to sign requests",
        "the baseline text used to detect edits",
        "this was used to compute x",
        "now returns a list",
        "moved to the service module",
        "use x instead of y",
        "the plan no longer matches what ran",
        "tools the server no longer offers",
        "inputs we can no longer describe",
        "picks from a previously cancelled dialog",
        "values changed from the saved config",
        "Phase 1: register as a waiter",
        "the output was removed after the batch",
    ],
)
def test_history_patterns_false_positive_guards(comment):
    assert not gate.has_history_phrase(comment)


def test_history_comment_only_scans_comment_text():
    assert rules_hit("a.py", 'msg = "no longer supported"') == []
    assert rules_hit("a.py", "x = 1  # no longer used") == ["history-comment"]
    assert rules_hit("a.svelte", "<p>Hi</p> <!-- previously a button -->") == [
        "history-comment"
    ]


@pytest.mark.parametrize(
    "path, text, expected",
    [
        ("a.py", "    global _cache", ["global-stmt"]),
        ("a.py", "global_cache = {}", []),
        ("a.py", 'flag = bool(os.getenv("X"))', ["bool-env", "env-access"]),
        ("a.py", 'flag = bool(os.environ.get("X"))', ["bool-env", "env-access"]),
        ("a.py", 'flag = parse_bool(os.environ.get("X"))', ["env-access"]),
        ("a.py", 'x = os.environ["X"]', ["env-access"]),
        ("a.py", "x = 1  # os.environ is read elsewhere", []),
        ("pkg/config.py", 'x = os.getenv("X")', []),
        ("entry/main.py", 'x = os.getenv("X")', []),
        (
            "libs/core/kiln_ai/x.py",
            "    key = Config.shared().api_key",
            ["core-config-shared"],
        ),
        ("libs/server/x.py", "    key = Config.shared().api_key", []),
    ],
)
def test_python_line_checks(path, text, expected):
    assert rules_hit(path, text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("setup_certs()", ["module-level-call"]),
        ('mimetypes.add_type("text/css", ".css")', ["module-level-call"]),
        ("    setup_certs()", []),
        ('if __name__ == "__main__":', []),
        ("print_banner = 1", []),
        ("app.include_router(router)", []),
        ("Usage (from repo root):", []),
        ("assert(x)", []),
        ("app = make_app()", ["module-level-construct"]),
        ("job_registry: JobRegistry = JobRegistry()", ["module-level-construct"]),
        ("    app = make_app()", []),
        ("x == make_app()", []),
        ("MAX = 3", []),
    ],
)
def test_module_level_checks(text, expected):
    assert rules_hit("pkg/mod.py", text) == expected


@pytest.mark.parametrize(
    "path, text, expected",
    [
        (
            "web/src/lib/a.ts",
            'import X from "../../routes/(app)/x.svelte"',
            ["lib-imports-routes"],
        ),
        (
            "web/src/lib/a.svelte",
            '  import X from "../routes/x.svelte"',
            ["lib-imports-routes"],
        ),
        (
            "web/src/lib/a.ts",
            'const m = await import("../routes/x")',
            ["lib-imports-routes"],
        ),
        ("web/src/lib/a.ts", 'import "../routes/side_effect"', ["lib-imports-routes"]),
        ("web/src/lib/a.ts", 'import { x } from "$lib/stores"', []),
        ("web/src/routes/a.ts", 'import X from "../routes/x.svelte"', []),
        ("web/src/lib/a.ts", "ui_state.subscribe((s) => {", ["module-level-subscribe"]),
        ("web/src/lib/a.ts", "  ui_state.subscribe((s) => {", []),
        ("web/src/routes/a.ts", "ui_state.subscribe((s) => {", []),
        ("web/src/lib/a.svelte", "ui_state.subscribe((s) => {", []),
    ],
)
def test_web_checks(path, text, expected):
    assert rules_hit(path, text) == expected


@pytest.mark.parametrize(
    "path",
    [
        "pkg/test_mod.py",
        "web/src/a.test.ts",
        "web/src/__tests__/a.svelte",
        "gen/x.py",
        "a.md",
    ],
)
def test_skipped_paths_are_not_checked(path):
    assert rules_hit(path, "global x  # no longer used") == []


def test_check_paths_and_exclude():
    cfg = make_config(
        checks={"global-stmt": {"paths": ["pkg/**"], "exclude": ["pkg/legacy/**"]}}
    )
    assert rules_hit("pkg/a.py", "global x", cfg) == ["global-stmt"]
    assert rules_hit("pkg/legacy/a.py", "global x", cfg) == []
    assert rules_hit("other/a.py", "global x", cfg) == []


def test_check_missing_from_config_is_disabled():
    cfg = make_config(checks={"global-stmt": {}})
    assert rules_hit("a.py", "x = 1  # no longer used", cfg) == []


def test_disabled_check_and_severity_override():
    cfg = make_config(
        checks={
            "global-stmt": {"severity": "WARN"},
            "history-comment": {"enabled": False},
        }
    )
    result = gate.run_checks([gate.Line("a.py", 1, "global x  # no longer")], cfg, [])
    assert [(hit.severity, hit.rule) for hit in result.hits] == [
        ("WARN", "global-stmt")
    ]


@pytest.mark.parametrize(
    "glob, path, matches",
    [
        ("**/test_*.py", "test_a.py", True),
        ("**/test_*.py", "a/b/test_a.py", True),
        ("**/test_*.py", "a/b/my_test_a.py", False),
        ("libs/core/**", "libs/core/a/b.py", True),
        ("libs/*.py", "libs/a/b.py", False),
        ("routes/[id]/*.ts", "routes/[id]/a.ts", True),
        ("routes/[id]/*.ts", "routes/i/a.ts", False),
        ("a?.py", "ab.py", True),
    ],
)
def test_glob_to_regex(glob, path, matches):
    assert bool(gate.glob_to_regex(glob).match(path)) is matches


def test_allowlist_scoped_and_unscoped_entries():
    allow = gate.parse_allowlist(
        "# reason\n\nglobal-stmt:pkg/a\\.py\n# reason\nother\\.py\t.*legacy\n",
        "allow",
    )
    assert [entry.rule for entry in allow] == ["global-stmt", None]
    lines = [
        gate.Line("pkg/a.py", 1, "global x  # no longer used"),
        gate.Line("other.py", 2, "global legacy  # no longer used"),
    ]
    result = gate.run_checks(lines, make_config(), allow)
    assert [(hit.path, hit.rule) for hit in result.hits] == [
        ("pkg/a.py", "history-comment")
    ]
    assert result.allowlisted == 3


def test_allowlist_prefix_that_is_not_a_rule_is_part_of_the_regex():
    (entry,) = gate.parse_allowlist("pkg/a.py:12", "allow")
    assert entry.rule is None
    assert entry.pattern.pattern == "pkg/a.py:12"


def test_invalid_allowlist_regex_names_the_line():
    with pytest.raises(gate.GateError, match="allow:2"):
        gate.parse_allowlist("# ok\nglobal-stmt:(unclosed\n", "allow")


@pytest.mark.parametrize(
    "config, message",
    [
        ({"checks": {"not-a-check": {}}}, "unknown check"),
        ({"checks": {"global-stmt": {"severity": "INFO"}}}, "severity"),
        ({"checks": {"global-stmt": {"enabled": "yes"}}}, "enabled"),
        ({"checks": {"global-stmt": {"pathz": []}}}, "unknown keys"),
        ({"checks": {"global-stmt": []}}, "must be an object"),
        ({"checks": []}, "must be an object"),
        ({"skip_globs": "x"}, "list of strings"),
        ({"module_level_call_ignore": ["("]}, "invalid regex"),
        ({"surprise": 1}, "unknown keys"),
        ([], "must be an object"),
    ],
)
def test_parse_config_errors(config, message):
    with pytest.raises(gate.GateError, match=message):
        gate.parse_config(config, "cfg")


def test_format_result_sorts_cuts_and_summarises():
    long_line = "global " + "x" * 300
    result = gate.Result(
        hits=[
            gate.Hit("WARN", "module-level-call", "b.py", 3, "  setup()  "),
            gate.Hit("FAIL", "global-stmt", "a.py", 9, long_line),
        ],
        allowlisted=2,
    )
    result.hits.sort(key=lambda hit: (hit.path, hit.lineno, hit.rule))
    lines = gate.format_result(result).split("\n")
    assert lines[0] == f"FAIL\tglobal-stmt\ta.py:9\t{long_line[:160]}"
    assert lines[1] == "WARN\tmodule-level-call\tb.py:3\tsetup()"
    assert lines[2] == "conventions_gate: 1 FAIL, 1 WARN, 2 allowlisted"


def test_run_checks_sorts_hits_by_path_and_line():
    lines = [
        gate.Line("b.py", 1, "global x"),
        gate.Line("a.py", 5, "global x"),
        gate.Line("a.py", 2, "global x"),
    ]
    result = gate.run_checks(lines, make_config(), [])
    assert [(hit.path, hit.lineno) for hit in result.hits] == [
        ("a.py", 2),
        ("a.py", 5),
        ("b.py", 1),
    ]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=gate@test", "-c", "user.name=gate", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "skill"
    directory.mkdir()
    (directory / "gate_config.json").write_text(json.dumps(BASE_CONFIG))
    (directory / "gate_allow.txt").write_text("# reason\nglobal-stmt:allowed\\.py\n")
    return directory


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "pkg").mkdir()
    (root / "pkg" / "mod.py").write_text("def f():\n    global old  # no longer\n")
    (root / "pkg" / "allowed.py").write_text("x = 1\n")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    return root


def run_main(args: list[str], config_dir: Path, capsys) -> tuple[int, list[str]]:
    code = gate.main(args, config_dir=config_dir)
    return code, capsys.readouterr().out.strip().split("\n")


def test_main_range_reports_only_added_lines(repo, config_dir, capsys):
    with (repo / "pkg" / "mod.py").open("a") as f:
        f.write("    global new\n")
    git(repo, "commit", "-qam", "change")
    code, out = run_main(
        ["--range", "HEAD~1..HEAD", "--repo", str(repo)], config_dir, capsys
    )
    assert code == 1
    assert out == [
        "FAIL\tglobal-stmt\tpkg/mod.py:3\tglobal new",
        "conventions_gate: 1 FAIL, 0 WARN, 0 allowlisted",
    ]


def test_main_worktree_includes_untracked_files(repo, config_dir, capsys):
    (repo / "pkg" / "allowed.py").write_text("x = 1\ndef g():\n    global y\n")
    (repo / "pkg" / "new.py").write_text("setup()\n")
    (repo / "notes.md").write_text("global z\n")
    code, out = run_main(["--worktree", "--repo", str(repo)], config_dir, capsys)
    assert code == 0
    assert out == [
        "WARN\tmodule-level-call\tpkg/new.py:1\tsetup()",
        "conventions_gate: 0 FAIL, 1 WARN, 1 allowlisted",
    ]


def test_main_files_reads_whole_files_and_directories(
    repo, config_dir, capsys, monkeypatch
):
    monkeypatch.chdir(repo)
    code, out = run_main(["--files", "pkg"], config_dir, capsys)
    assert code == 1
    assert out == [
        "FAIL\tglobal-stmt\tpkg/mod.py:2\tglobal old  # no longer",
        "FAIL\thistory-comment\tpkg/mod.py:2\tglobal old  # no longer",
        "conventions_gate: 2 FAIL, 0 WARN, 0 allowlisted",
    ]
    code, out = run_main(["--files", "pkg/allowed.py"], config_dir, capsys)
    assert (code, out) == (0, ["conventions_gate: 0 FAIL, 0 WARN, 0 allowlisted"])


def test_main_skips_undecodable_files(repo, config_dir, capsys):
    (repo / "pkg" / "binary.py").write_bytes(b"\xff\xfe global x\n")
    code, out = run_main(["--worktree", "--repo", str(repo)], config_dir, capsys)
    assert (code, out) == (0, ["conventions_gate: 0 FAIL, 0 WARN, 0 allowlisted"])


@pytest.mark.parametrize(
    "args",
    [
        ["--range", "no-such-ref..HEAD"],
        ["--files", "does/not/exist.py"],
    ],
)
def test_main_git_and_path_errors_exit_2(repo, config_dir, capsys, monkeypatch, args):
    monkeypatch.chdir(repo)
    assert gate.main(args, config_dir=config_dir) == 2
    assert "conventions_gate: error:" in capsys.readouterr().err


def test_main_outside_a_repo_exits_2(tmp_path, config_dir, capsys):
    outside = tmp_path / "plain"
    outside.mkdir()
    assert gate.main(["--worktree", "--repo", str(outside)], config_dir=config_dir) == 2
    assert "rev-parse" in capsys.readouterr().err


def test_main_missing_config_exits_2(repo, tmp_path, capsys):
    assert gate.main(["--worktree", "--repo", str(repo)], config_dir=tmp_path) == 2
    assert "config not found" in capsys.readouterr().err


def test_main_invalid_allowlist_exits_2(repo, config_dir, capsys):
    (config_dir / "gate_allow.txt").write_text("[unclosed\n")
    assert gate.main(["--worktree", "--repo", str(repo)], config_dir=config_dir) == 2
    assert "gate_allow.txt:1" in capsys.readouterr().err


def test_main_usage_error_exits_2(config_dir):
    with pytest.raises(SystemExit) as exc:
        gate.main([], config_dir=config_dir)
    assert exc.value.code == 2


def test_script_runs_standalone_with_shipped_config(repo):
    proc = subprocess.run(
        [sys.executable, str(GATE_PATH), "--worktree", "--repo", str(repo)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("0 FAIL, 0 WARN, 0 allowlisted")
