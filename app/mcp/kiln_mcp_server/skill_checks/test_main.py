from kiln_mcp_server.conftest import write_tree
from kiln_mcp_server.skill_checks.__main__ import main

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
            "references/orphan.md": "x\n",
        },
    )
    assert main(["check", "--root", str(root)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "tree-path  SKILL.md  line 7: `references/nope.md` is not a file or folder of the skill",
        "tree-unreachable  references/orphan.md  not reached from SKILL.md",
        "2 problems",
    ]


def test_a_missing_folder_exits_2(tmp_path, capsys):
    assert main(["check", "--root", str(tmp_path / "missing")]) == 2
    assert "No skill folder at" in capsys.readouterr().err


def test_the_default_root_is_the_shipped_tree():
    assert main(["check"]) == 0
