import json

import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill, SkillProvenance
from kiln_ai.datamodel.skill_bundle import (
    MAX_BUNDLE_BYTES,
    MAX_RESOURCE_FILE_BYTES,
    STAGING_DIR_NAME,
    SkillBundleValidationError,
    clone_skill,
    create_skill_with_files,
    validate_resource_path,
)


@pytest.fixture
def project(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


BODY = "## Instructions\n\nDo the thing."


def create(project, name="my-skill", files=None, **kwargs):
    return create_skill_with_files(
        project,
        name=name,
        description="A test skill.",
        body=BODY,
        files=files,
        **kwargs,
    )


class TestValidateResourcePath:
    @pytest.mark.parametrize(
        "path",
        [
            "references/guide.md",
            "references/api/endpoints.md",
            "assets/logo.png",
            "assets/deep/nested/file.bin",
        ],
    )
    def test_valid_paths(self, path):
        assert validate_resource_path(path) is None

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("", "cannot be empty"),
            ("   ", "cannot be empty"),
            ("references\\guide.md", "forward slashes"),
            ("scripts/run.py", "must start with"),
            ("SKILL.md", "must start with"),
            ("references", "must include a filename"),
            ("references/", "must include a filename"),
            ("references/../secret", "invalid segment"),
            ("references/./guide.md", "invalid segment"),
            ("references//guide.md", "invalid segment"),
            ("assets/foo\x00bar", "null byte"),
        ],
    )
    def test_invalid_paths(self, path, expected):
        error = validate_resource_path(path)
        assert error is not None and expected in error


class TestCreateSkillWithFiles:
    def test_create_without_files(self, project):
        skill = create(project)
        assert skill.path is not None
        skill_dir = skill.path.parent
        assert skill_dir.parent == project.path.parent / "skills"
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "references").is_dir()
        assert (skill_dir / "assets").is_dir()
        loaded = Skill.load_from_file(skill.path)
        assert loaded.name == "my-skill"
        assert loaded.body() == BODY

    def test_create_with_files(self, project):
        files = {
            "references/guide.md": b"# Guide",
            "references/api/endpoints.md": b"# Endpoints",
            "assets/logo.png": b"\x89PNG\x00binary",
        }
        skill = create(project, files=files)
        assert skill.list_resource_files() == sorted(files.keys())
        assert skill.read_resource_bytes("assets/logo.png") == b"\x89PNG\x00binary"
        assert skill.read_reference("api/endpoints.md") == "# Endpoints"

    def test_provenance_persisted(self, project):
        provenance = SkillProvenance(
            notes="why this exists", derived_from_ids=["111"], origin="agent"
        )
        skill = create(project, provenance=provenance)
        loaded = Skill.load_from_file(skill.path)
        assert loaded.provenance == provenance
        raw = json.loads(skill.path.read_text(encoding="utf-8"))
        assert raw["provenance"]["origin"] == "agent"

    def test_duplicate_name_rejected(self, project):
        create(project)
        with pytest.raises(SkillBundleValidationError, match="install-once"):
            create(project)

    def test_errors_accumulate(self, project):
        create(project, name="taken")
        with pytest.raises(SkillBundleValidationError) as exc_info:
            create_skill_with_files(
                project,
                name="taken",
                description="A test skill.",
                body="  ",
                files={
                    "scripts/run.py": b"print()",
                    "references/bad.md": b"\xff\xfe not utf8",
                },
            )
        errors = exc_info.value.errors
        assert len(errors) == 4
        assert any("must start with" in e for e in errors)
        assert any("not UTF-8" in e for e in errors)
        assert any("body must be non-empty" in e for e in errors)
        assert any("install-once" in e for e in errors)

    def test_file_too_large_rejected(self, project):
        files = {"assets/big.bin": b"x" * (MAX_RESOURCE_FILE_BYTES + 1)}
        with pytest.raises(SkillBundleValidationError, match="file too large"):
            create(project, files=files)

    def test_bundle_too_large_rejected(self, project):
        per_file = MAX_RESOURCE_FILE_BYTES
        count = MAX_BUNDLE_BYTES // per_file + 1
        files = {f"assets/big{i}.bin": b"x" * per_file for i in range(count)}
        with pytest.raises(SkillBundleValidationError, match="bundle too large"):
            create(project, files=files)

    def test_rejected_bundle_writes_nothing(self, project):
        with pytest.raises(SkillBundleValidationError):
            create(project, files={"scripts/run.py": b"nope"})
        skills_dir = project.path.parent / "skills"
        assert not skills_dir.exists() or not any(skills_dir.iterdir())

    def test_no_staging_debris_left_behind(self, project):
        create(project, files={"references/a.md": b"a"})
        staging_root = project.path.parent / STAGING_DIR_NAME
        assert not staging_root.exists() or not any(staging_root.iterdir())

    def test_binary_reference_rejected(self, project):
        with pytest.raises(SkillBundleValidationError, match="not UTF-8"):
            create(project, files={"references/binary.bin": b"\x89PNG\x00"})

    def test_binary_asset_allowed(self, project):
        skill = create(project, files={"assets/binary.bin": b"\x89PNG\x00"})
        assert skill.read_resource_bytes("assets/binary.bin") == b"\x89PNG\x00"

    def test_skill_visible_via_project_children(self, project):
        skill = create(project)
        names = [s.name for s in project.skills(readonly=True)]
        assert names == [skill.name]


class TestCloneSkill:
    @pytest.fixture
    def source(self, project):
        return create(
            project,
            name="source-skill",
            files={
                "references/guide.md": b"# Guide",
                "assets/logo.png": b"\x89PNG\x00",
            },
        )

    def test_clone_copies_resources(self, project, source):
        clone = clone_skill(
            project,
            source,
            name="cloned-skill",
            description="A clone.",
            body="New body.",
        )
        assert clone.list_resource_files() == source.list_resource_files()
        assert clone.read_resource_bytes("assets/logo.png") == b"\x89PNG\x00"
        assert clone.body() == "New body."
        assert clone.id != source.id

    def test_clone_records_lineage(self, project, source):
        clone = clone_skill(
            project,
            source,
            name="cloned-skill",
            description="A clone.",
            body="New body.",
        )
        assert clone.provenance is not None
        assert clone.provenance.derived_from_ids == [source.id]
        assert clone.provenance.origin == "user"

    def test_clone_does_not_mutate_source(self, project, source):
        clone_skill(
            project,
            source,
            name="cloned-skill",
            description="A clone.",
            body="New body.",
        )
        assert source.read_reference("guide.md") == "# Guide"
        assert source.body() == BODY

    def test_clone_rejects_duplicate_name(self, project, source):
        with pytest.raises(SkillBundleValidationError, match="install-once"):
            clone_skill(
                project,
                source,
                name="source-skill",
                description="A clone.",
                body="New body.",
            )
