import pytest

from kiln_mcp_server.conftest import write_tree
from kiln_mcp_server.skill_files import (
    API_CATALOGUE_INDEX_PATH,
    DEFAULT_ORIGIN,
    E_ABS,
    E_CTRL,
    E_SCHEME,
    E_SKILL,
    E_UP,
    HINT,
    SkillIndex,
    SkillPathError,
    apply_origin,
    build_index,
    read_file,
    read_skill,
    resolve_path,
    strip_front_matter,
)

SKILL_MD = "---\nname: kiln\ndescription: Test skill.\n---\n\n# Kiln\n\nRead `references/knowledge/rag.md`.\n"
RAG_MD = "---\nname: rag\ndescription: RAG.\n---\n\nOpen http://localhost:8757/docs/{project_id}.\n"

TREE = {
    "SKILL.md": SKILL_MD,
    "references/knowledge/rag.md": RAG_MD,
    "references/knowledge/specs_and_evals.md": "Specs.\n",
    "references/knowledge/api_docs/api_index.md": "Catalogues.\n",
    "references/knowledge/api_docs/projects_api_list.md": "Projects.\n",
    "references/knowledge/api_docs/get_api_projects.md": "GET.\n",
    "references/knowledge/api_docs/post_api_projects.md": "POST.\n",
    "references/modes/learn.md": "Learn.\n",
    "references/docs/README.md": "Docs.\n",
}

HIDDEN = {
    ".hidden/secret.md": "x",
    "references/.DS_Store": "x",
    "__pycache__/x.md": "x",
    "references/__pycache__/y.md": "x",
}


@pytest.fixture
def index(tmp_path) -> SkillIndex:
    return build_index(write_tree(tmp_path / "skill", {**TREE, **HIDDEN}))


def test_index_holds_skill_md_and_posix_keys(index):
    assert list(index.files) == sorted(TREE)
    assert index.folders == {
        "",
        "references",
        "references/knowledge",
        "references/knowledge/api_docs",
        "references/modes",
        "references/docs",
    }


def test_index_without_skill_md_raises(tmp_path):
    root = write_tree(tmp_path / "skill", {"references/modes/learn.md": "x"})
    with pytest.raises(
        RuntimeError,
        match=r"^Kiln skill files are missing from the package \(no SKILL\.md\)$",
    ):
        build_index(root)


def test_index_of_a_missing_folder_raises(tmp_path):
    with pytest.raises(RuntimeError, match=r"no SKILL\.md"):
        build_index(tmp_path / "nope")


def test_index_skips_hidden_and_pycache(index):
    assert not any(
        part.startswith(".") or part == "__pycache__"
        for key in index.files
        for part in key.split("/")
    )


RAG = "references/knowledge/rag.md"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("SKILL.md", None),
        ("./SKILL.md", None),
        ("skill://kiln", None),
        ("skill://kiln/SKILL.md", None),
        ("SKILL://Kiln/SKILL.md", None),
        ("``", None),
        (RAG, RAG),
        ("./references/knowledge/rag.md", RAG),
        ("skill://kiln/references/knowledge/rag.md", RAG),
        ("references\\knowledge\\rag.md", RAG),
        ("`references/knowledge/rag.md`", RAG),
        ("'references/knowledge/rag.md'", RAG),
        ('"references/knowledge/rag.md"', RAG),
        (" ` references/knowledge/rag.md ` ", RAG),
        ("references//knowledge/rag.md", RAG),
        ("references/knowledge/rag.md#setup", RAG),
        ("references/knowledge/rag.md?x=1", RAG),
    ],
)
def test_resolve_path(raw, expected, index):
    assert resolve_path(raw, index) == expected


@pytest.mark.parametrize(
    ("raw", "template"),
    [
        ("/etc/passwd", E_ABS),
        ("~/x", E_ABS),
        ("C:\\x", E_ABS),
        ("c:/x", E_ABS),
        ("\\\\host\\share", E_ABS),
        ("skill://kiln//etc/passwd", E_ABS),
        ("../x", E_UP),
        ("references/../SKILL.md", E_UP),
        ("https://x/y.md", E_SCHEME),
        ("file:///etc/passwd", E_SCHEME),
        ("skill://other/x.md", E_SKILL),
        ("skill://", E_SKILL),
    ],
)
def test_resolve_path_refusals(raw, template, index):
    with pytest.raises(SkillPathError) as error:
        resolve_path(raw, index)
    assert error.value.message == template.format(raw=raw)


def test_each_error_text():
    assert HINT == (
        "Give a path relative to the skill root, exactly as the skill's instructions "
        "wrote it, for example `references/knowledge/specs_and_evals.md`. "
        "Omit the path to read the skill's instructions."
    )
    assert E_ABS.format(raw="/x") == "Refused: `/x` is an absolute path. " + HINT
    assert E_UP.format(raw="../x") == (
        "Refused: `../x` leaves the skill root. `..` is not allowed in a skill path. "
        + HINT
    )
    assert E_SCHEME.format(raw="https://x") == (
        "Refused: `https://x` is not a skill path. " + HINT
    )
    assert E_SKILL.format(raw="skill://other") == (
        "Refused: `skill://other` names another skill. "
        "This tool serves one skill, `kiln`. " + HINT
    )
    assert E_CTRL == "Refused: the path holds a control character. " + HINT


@pytest.mark.parametrize("raw", ["references/\x00rag.md", "a\tb", "x\ny"])
def test_control_character_is_refused(raw, index):
    with pytest.raises(SkillPathError) as error:
        resolve_path(raw, index)
    assert error.value.message == E_CTRL


def _miss(raw: str, index: SkillIndex) -> str:
    with pytest.raises(SkillPathError) as error:
        resolve_path(raw, index)
    return error.value.message


def test_not_found_lists_nearest_folder(index):
    assert _miss("references/knowledge/nope.md", index) == (
        "No skill file at `references/knowledge/nope.md`.\n"
        "Files in `references/knowledge`:\n"
        "references/knowledge/rag.md\n"
        "references/knowledge/specs_and_evals.md\n"
        "Folders in `references/knowledge`:\n"
        "references/knowledge/api_docs/\n"
        "Copy a path exactly as the skill's instructions wrote it."
    )


def test_not_found_lists_sub_folders(index):
    assert _miss("references/nope/deeper/x.md", index) == (
        "No skill file at `references/nope/deeper/x.md`.\n"
        "Files in `references`:\n"
        "(none)\n"
        "Folders in `references`:\n"
        "references/docs/\n"
        "references/knowledge/\n"
        "references/modes/\n"
        "Copy a path exactly as the skill's instructions wrote it."
    )


def test_not_found_at_the_root(index):
    assert _miss("nope.md", index) == (
        "No skill file at `nope.md`.\n"
        "Files in the skill root:\n"
        "SKILL.md\n"
        "Folders in the skill root:\n"
        "references/\n"
        "Copy a path exactly as the skill's instructions wrote it."
    )


def test_not_found_suggests_case_fix(index):
    message = _miss("References/Knowledge/RAG.md", index)
    assert message.startswith(
        "No skill file at `References/Knowledge/RAG.md`. "
        "Did you mean `references/knowledge/rag.md`?\n"
        "Files in the skill root:\n"
    )


@pytest.mark.parametrize("raw", ["references/knowledge", "references/knowledge/"])
def test_folder_path_is_an_error(raw, index):
    message = _miss(raw, index)
    assert message.startswith(
        f"No skill file at `{raw}`. `references/knowledge` is a folder, not a file.\n"
        "Files in `references/knowledge`:\n"
        "references/knowledge/rag.md\n"
    )


def test_api_docs_listing_is_short(index):
    assert _miss("references/knowledge/api_docs/get_api_nope.md", index) == (
        "No skill file at `references/knowledge/api_docs/get_api_nope.md`.\n"
        "Files in `references/knowledge/api_docs`:\n"
        f"{API_CATALOGUE_INDEX_PATH}\n"
        "references/knowledge/api_docs/projects_api_list.md\n"
        "Plus 2 endpoint docs, not listed. Find an endpoint doc through a catalogue.\n"
        "Copy a path exactly as the skill's instructions wrote it."
    )


def test_raw_is_cleaned_and_cut(index):
    # Surrounding whitespace, control characters included, is stripped before
    # the checks but is still part of the argument as received.
    raw = "\t/`y`" + "y" * 300 + "\n"
    with pytest.raises(SkillPathError) as error:
        resolve_path(raw, index)
    assert error.value.message == E_ABS.format(raw=("/" + "y" * 301)[:200])


def test_raw_in_not_found_is_cleaned_and_cut(index):
    raw = "`nope`" + "z" * 300
    first_line = _miss(raw, index).split("\n")[0]
    assert first_line == f"No skill file at `{('nope' + 'z' * 300)[:200]}`."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\nname: kiln\n---\n\n\n# Kiln\n", "# Kiln\n"),
        ("---\nname: kiln\n---\n  \n# Kiln\n", "# Kiln\n"),
        ("# Kiln\n---\n", "# Kiln\n---\n"),
        ("---\nname: kiln\n# never closed\n", "---\nname: kiln\n# never closed\n"),
        ("", ""),
    ],
)
def test_strip_front_matter(text, expected):
    assert strip_front_matter(text) == expected


def test_root_is_served_without_front_matter(index):
    assert read_skill(None, DEFAULT_ORIGIN, index) == (
        "# Kiln\n\nRead `references/knowledge/rag.md`.\n"
    )


def test_reference_file_keeps_front_matter(index):
    assert read_skill(RAG, DEFAULT_ORIGIN, index) == RAG_MD


def test_apply_origin_only_when_different():
    text = "See http://localhost:8757/x and http://localhost:8757/y."
    assert apply_origin(text, DEFAULT_ORIGIN) is text
    assert apply_origin(text, "http://localhost:9000") == (
        "See http://localhost:9000/x and http://localhost:9000/y."
    )


def test_read_skill_applies_the_origin(index):
    assert "http://kiln.lan:8757/docs/" in read_skill(
        RAG, "http://kiln.lan:8757", index
    )


def test_read_is_byte_exact(tmp_path):
    text = "---\nname: x\n---\r\nline one\r\nnon-ascii: \u00e9\u4e2d\n\n"
    index = build_index(write_tree(tmp_path / "skill", {"SKILL.md": "x", "a.md": text}))
    assert read_file("a.md", index) == text


def test_read_skill_raises_for_a_missing_file(index):
    with pytest.raises(SkillPathError):
        read_skill("nope.md", DEFAULT_ORIGIN, index)
