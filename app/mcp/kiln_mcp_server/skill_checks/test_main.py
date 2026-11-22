from kiln_mcp_server.conftest import write_tree
from kiln_mcp_server.skill_checks.__main__ import main
from kiln_mcp_server.skill_checks.docs_index import DOCS_INDEX_PATH
from kiln_mcp_server.skill_checks.knowledge_schema import default_root
from kiln_mcp_server.skill_checks.test_knowledge_check import (
    IMPROVING_INDEX,
    TECHNIQUE,
    TECHNIQUES,
    build_tree,
)
from kiln_mcp_server.skill_checks.test_shipped_skill import PENDING_RULES

SKILL_MD = "---\nname: kiln\ndescription: Work with Kiln.\n---\n\n# Kiln\n"


def test_a_clean_tree_exits_0(tmp_path, capsys):
    root = write_tree(tmp_path / "skill", {"SKILL.md": SKILL_MD})
    assert main(["check", "--root", str(root)]) == 0
    assert capsys.readouterr().out == ""


def test_problems_exit_1_with_one_line_each(tmp_path, capsys):
    root = write_tree(
        tmp_path / "skill",
        {
            "SKILL.md": SKILL_MD + "Read `references/nope.md`.\n",
            "references/notes/orphan.md": "x\n",
        },
    )
    assert main(["check", "--root", str(root)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "tree-path  SKILL.md  line 7: `references/nope.md` is not a file or folder of the skill",
        "tree-unreachable  references/notes/orphan.md  not reached from SKILL.md",
        "2 problems",
    ]


def test_a_missing_folder_exits_2(tmp_path, capsys):
    assert main(["check", "--root", str(tmp_path / "missing")]) == 2
    assert "No skill folder at" in capsys.readouterr().err


def test_the_default_root_is_the_shipped_tree(capsys):
    code = main(["check"])
    default_out = capsys.readouterr().out
    assert main(["check", "--root", str(default_root())]) == code
    assert capsys.readouterr().out == default_out
    problem_lines = default_out.splitlines()[:-1] if code else []
    assert {line.split("  ", 1)[0] for line in problem_lines} <= PENDING_RULES


def test_build_rewrites_the_indexes_then_checks(tmp_path, capsys):
    tree = build_tree(tmp_path)
    tree.write(f"{TECHNIQUES}/t-two.md", TECHNIQUE.replace("One technique", "Two"))
    tree.write("references/docs/evals.md", "---\nonline_url: x\n---\n# Evals\n")
    assert main(["check", "--root", str(tree.root)]) == 1
    capsys.readouterr()

    assert main(["build", "--root", str(tree.root)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[:2] == [
        f"rewrote {tree.root / IMPROVING_INDEX}",
        f"rewrote {tree.root / DOCS_INDEX_PATH}",
    ]
    # The help article is not reachable from SKILL.md, and its online_url is
    # wrong: build rewrites indexes only.
    assert {line.split("  ")[0] for line in out[2:-1]} == {
        "tree-front-matter",
        "tree-unreachable",
    }
    assert "t-two" in tree.read(IMPROVING_INDEX)


def test_build_on_a_current_tree_rewrites_nothing(tmp_path, capsys):
    tree = build_tree(tmp_path)
    assert main(["build", "--root", str(tree.root)]) == 0
    assert capsys.readouterr().out == ""


def test_check_reports_a_stale_knowledge_index(tmp_path, capsys):
    tree = build_tree(tmp_path)
    tree.edit(f"{TECHNIQUES}/t-one.md", "which edits the prompt", "which changes it")
    assert main(["check", "--root", str(tree.root)]) == 1
    assert f"index  {IMPROVING_INDEX}  the block 'techniques' is stale" in (
        capsys.readouterr().out
    )


def test_build_with_a_missing_folder_exits_2(tmp_path):
    assert main(["build", "--root", str(tmp_path / "missing")]) == 2
