import pytest

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.skill import Skill
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
            ("references/bad:name.md", "not allowed on Windows"),
            ("references/bad?.md", "not allowed on Windows"),
            ("references/a\tb.md", "not allowed on Windows"),
            ("references/name.", "must not end with a dot or space"),
            ("references/name ", "must not end with a dot or space"),
            ("references/CON.md", "reserved on Windows"),
            ("assets/com1", "reserved on Windows"),
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
        assert [p for p, _ in skill.list_resources_with_sizes()] == sorted(files.keys())
        assert skill.read_resource_bytes("assets/logo.png") == b"\x89PNG\x00binary"
        assert skill.read_reference("api/endpoints.md") == "# Endpoints"

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
        # The staging root itself is removed so it never lingers in a synced
        # project folder.
        staging_root = project.path.parent / STAGING_DIR_NAME
        assert not staging_root.exists()

    def test_disk_full_propagates_as_oserror(self, project):
        import errno as errno_mod
        from unittest.mock import patch

        with patch.object(
            Skill,
            "save_skill_md",
            side_effect=OSError(errno_mod.ENOSPC, "No space left on device"),
        ):
            with pytest.raises(OSError) as exc_info:
                create(project)
        # Environment failures are not the caller's fault: no 422-style error.
        assert not isinstance(exc_info.value, SkillBundleValidationError)
        staging_root = project.path.parent / STAGING_DIR_NAME
        assert not staging_root.exists()

    def test_staging_root_squatted_by_file_is_clear_error(self, project):
        (project.path.parent / STAGING_DIR_NAME).write_text(
            "sync conflict artifact", encoding="utf-8"
        )
        with pytest.raises(SkillBundleValidationError, match="remove it and retry"):
            create(project)

    def test_invalid_filename_oserror_becomes_validation_error(self, project):
        import errno as errno_mod
        from unittest.mock import patch

        with patch.object(
            Skill,
            "save_skill_md",
            side_effect=OSError(errno_mod.EINVAL, "Invalid argument"),
        ):
            with pytest.raises(
                SkillBundleValidationError, match="could not write skill files"
            ):
                create(project)

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

    def test_file_and_directory_conflict_rejected(self, project):
        files = {
            "references/foo": b"a file",
            "references/foo/bar.md": b"needs foo as a directory",
        }
        with pytest.raises(
            SkillBundleValidationError, match="both a file and a directory"
        ):
            create(project, files=files)

    def test_case_insensitive_duplicate_rejected(self, project):
        files = {
            "references/Guide.md": b"a",
            "references/guide.md": b"b",
        }
        with pytest.raises(SkillBundleValidationError, match="collide on a case"):
            create(project, files=files)

    def test_unicode_normalization_collision_rejected(self, project):
        # NFC and NFD spellings of the same name are one file on APFS/HFS+.
        files = {
            "references/caf\u00e9.md": b"a",
            "references/cafe\u0301.md": b"b",
        }
        with pytest.raises(SkillBundleValidationError, match="collide on a case"):
            create(project, files=files)

    def test_too_many_files_rejected(self, project):
        from kiln_ai.datamodel.skill_bundle import MAX_BUNDLE_FILE_COUNT

        files = {f"assets/f{i}.bin": b"" for i in range(MAX_BUNDLE_FILE_COUNT + 1)}
        with pytest.raises(SkillBundleValidationError, match="too many files"):
            create(project, files=files)

    def test_files_and_copy_files_overlap_rejected(self, project, tmp_path):
        on_disk = tmp_path / "on_disk.md"
        on_disk.write_text("disk", encoding="utf-8")
        with pytest.raises(
            SkillBundleValidationError, match="both files and copy_files"
        ):
            create_skill_with_files(
                project,
                name="overlap-skill",
                description="A test skill.",
                body=BODY,
                files={"references/a.md": b"inline"},
                copy_files={"references/a.md": on_disk},
            )

    def test_files_and_copy_files_cross_conflict_rejected(self, project, tmp_path):
        on_disk = tmp_path / "on_disk.md"
        on_disk.write_text("disk", encoding="utf-8")
        with pytest.raises(
            SkillBundleValidationError, match="both a file and a directory"
        ):
            create_skill_with_files(
                project,
                name="conflict-skill",
                description="A test skill.",
                body=BODY,
                files={"references/a": b"inline"},
                copy_files={"references/a/b.md": on_disk},
            )

    def test_skills_dirname_squatted_by_file_is_clear_error(self, project):
        (project.path.parent / "skills").write_text(
            "sync conflict artifact", encoding="utf-8"
        )
        with pytest.raises(SkillBundleValidationError, match="remove it and retry"):
            create(project)

    def test_unreadable_sibling_skill_does_not_block_create(self, project):
        broken_dir = project.path.parent / "skills" / "123456789012 - broken"
        broken_dir.mkdir(parents=True)
        (broken_dir / "skill.kiln").write_text("not json{", encoding="utf-8")
        skill = create(project)
        assert skill.name == "my-skill"

    def test_archived_name_conflict_mentions_archived(self, project):
        skill = create(project)
        loaded = Skill.load_from_file(skill.path)
        loaded.is_archived = True
        loaded.save_to_file()
        with pytest.raises(SkillBundleValidationError, match="archived skill"):
            create(project)

    def test_stale_staging_swept_fresh_staging_kept(self, project):
        import os as os_mod
        import time as time_mod

        from kiln_ai.datamodel.skill_bundle import STALE_STAGING_AGE_SECS

        staging_root = project.path.parent / STAGING_DIR_NAME
        staging_root.mkdir()
        stale = staging_root / "skill-stale"
        stale.mkdir()
        old_time = time_mod.time() - STALE_STAGING_AGE_SECS - 60
        os_mod.utime(stale, (old_time, old_time))
        fresh = staging_root / "skill-fresh"
        fresh.mkdir()
        create(project)
        assert not stale.exists()
        assert fresh.exists()


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
        assert clone.list_resources_with_sizes() == source.list_resources_with_sizes()
        assert clone.read_resource_bytes("assets/logo.png") == b"\x89PNG\x00"
        assert clone.body() == "New body."
        assert clone.id != source.id

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

    def test_clone_allows_oversized_on_disk_files(self, project, source):
        big = source.assets_dir() / "big.bin"
        big.write_bytes(b"x" * (MAX_RESOURCE_FILE_BYTES + 1))
        clone = clone_skill(
            project,
            source,
            name="cloned-skill",
            description="A clone.",
            body="New body.",
        )
        assert clone.read_resource_bytes("assets/big.bin") == b"x" * (
            MAX_RESOURCE_FILE_BYTES + 1
        )

    def test_clone_copies_files_outside_resource_dirs(self, project, source):
        assert source.path is not None
        source_dir = source.path.parent
        scripts_dir = source_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.py").write_text("print('hi')", encoding="utf-8")
        (source_dir / "docs.md").write_text("# Docs", encoding="utf-8")
        clone = clone_skill(
            project,
            source,
            name="cloned-skill",
            description="A clone.",
            body="New body.",
        )
        assert clone.path is not None
        clone_dir = clone.path.parent
        assert (clone_dir / "scripts" / "run.py").read_text(
            encoding="utf-8"
        ) == "print('hi')"
        assert (clone_dir / "docs.md").read_text(encoding="utf-8") == "# Docs"
        # skill.kiln and SKILL.md are regenerated, never copied
        assert Skill.load_from_file(clone.path).id != source.id

    def test_clone_allows_backslash_in_filename(self, project, source):
        # A backslash is a legal filename character on POSIX; hand-added
        # files must not make a skill uncloneable.
        weird = source.references_dir() / "notes\\draft.md"
        weird.write_text("draft", encoding="utf-8")
        clone = clone_skill(
            project,
            source,
            name="cloned-skill",
            description="A clone.",
            body="New body.",
        )
        assert clone.path is not None
        assert (clone.path.parent / "references" / "notes\\draft.md").read_text(
            encoding="utf-8"
        ) == "draft"

    def test_clone_skips_file_vanished_mid_copy(self, project, source):
        import shutil as shutil_mod
        from unittest.mock import patch

        real_copyfile = shutil_mod.copyfile

        def flaky_copyfile(src, dst, **kwargs):
            if str(src).endswith("guide.md"):
                raise FileNotFoundError(src)
            return real_copyfile(src, dst, **kwargs)

        with patch("kiln_ai.datamodel.skill_bundle.shutil.copyfile", flaky_copyfile):
            clone = clone_skill(
                project,
                source,
                name="cloned-skill",
                description="A clone.",
                body="New body.",
            )
        assert [p for p, _ in clone.list_resources_with_sizes()] == ["assets/logo.png"]

    def test_clone_preserves_empty_directories(self, project, source):
        assert source.path is not None
        (source.path.parent / "assets" / "output").mkdir()
        (source.path.parent / "scripts").mkdir()
        clone = clone_skill(
            project,
            source,
            name="cloned-skill",
            description="A clone.",
            body="New body.",
        )
        assert clone.path is not None
        assert (clone.path.parent / "assets" / "output").is_dir()
        assert (clone.path.parent / "scripts").is_dir()

    def test_clone_allows_case_variant_files_on_case_sensitive_fs(
        self, project, source
    ):
        # Hand-added files differing only by case coexist on a case-sensitive
        # filesystem; cloning onto the same filesystem must not reject them.
        (source.references_dir() / "Notes.md").write_text("A", encoding="utf-8")
        (source.references_dir() / "notes.md").write_text("b", encoding="utf-8")
        clone = clone_skill(
            project,
            source,
            name="cloned-skill",
            description="A clone.",
            body="New body.",
        )
        assert clone.read_reference("Notes.md") == "A"
        assert clone.read_reference("notes.md") == "b"

    def test_clone_rejects_duplicate_name(self, project, source):
        with pytest.raises(SkillBundleValidationError, match="install-once"):
            clone_skill(
                project,
                source,
                name="source-skill",
                description="A clone.",
                body="New body.",
            )
