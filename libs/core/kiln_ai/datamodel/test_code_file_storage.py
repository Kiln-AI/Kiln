"""Unit tests for the shared sibling-code-file storage helper.

These test `read_code_from_sibling_file` / `write_code_to_sibling_file` directly,
in isolation from the CodeTool / CodeEvalProperties models that call them. The
model-level, end-to-end behavior is covered in test_code_tool.py and
test_eval_model.py.
"""

import pytest

from kiln_ai.datamodel.code_file_storage import (
    _require_bare_filename,
    read_code_from_sibling_file,
    write_code_to_sibling_file,
)

FILENAME = "tool.py"
KILN_FILENAME = "code_tool.kiln"
MODEL_LABEL = "CodeTool"
CODE = "def run(x):\n    return x\n"


def _load(data, ctx):
    return read_code_from_sibling_file(
        data,
        ctx,
        filename=FILENAME,
        kiln_filename=KILN_FILENAME,
        model_label=MODEL_LABEL,
    )


def _save(data, ctx, code=CODE):
    return write_code_to_sibling_file(data, ctx, filename=FILENAME, code=code)


class TestReadCodeFromSiblingFile:
    def test_injects_code_from_file(self, tmp_path):
        (tmp_path / FILENAME).write_text(CODE, encoding="utf-8")
        result = _load(
            {"name": "My Tool"},
            {"loading_from_file": True, "source_dir": tmp_path},
        )
        assert result["code"] == CODE
        assert result["name"] == "My Tool"

    def test_missing_source_dir_errors(self):
        with pytest.raises(ValueError, match="source_dir missing from load context"):
            _load({"name": "My Tool"}, {"loading_from_file": True})

    def test_missing_source_dir_error_names_model(self):
        with pytest.raises(ValueError, match="Cannot load CodeTool"):
            _load({"name": "My Tool"}, {"loading_from_file": True})

    def test_unreadable_file_errors_naming_file_and_path(self, tmp_path):
        # No tool.py written -> read fails; message names the .kiln, the sibling
        # filename, and the expected full path.
        with pytest.raises(ValueError) as exc_info:
            _load(
                {"name": "My Tool"},
                {"loading_from_file": True, "source_dir": tmp_path},
            )
        message = str(exc_info.value)
        assert KILN_FILENAME in message
        assert FILENAME in message
        assert str(tmp_path / FILENAME) in message

    def test_lenient_when_code_already_present(self, tmp_path):
        # A dict that already carries `code` is used as-is; the sibling file is
        # never read (write a different body to prove it is ignored).
        (tmp_path / FILENAME).write_text(
            "def run(x):\n    return 999\n", encoding="utf-8"
        )
        result = _load(
            {"name": "My Tool", "code": CODE},
            {"loading_from_file": True, "source_dir": tmp_path},
        )
        assert result["code"] == CODE

    def test_skips_when_not_loading_from_file(self, tmp_path):
        (tmp_path / FILENAME).write_text(CODE, encoding="utf-8")
        data = {"name": "My Tool"}
        # No loading_from_file flag: nothing is read, `code` stays absent.
        result = _load(data, {"source_dir": tmp_path})
        assert "code" not in result

    def test_non_dict_data_passes_through(self, tmp_path):
        (tmp_path / FILENAME).write_text(CODE, encoding="utf-8")
        sentinel = ["not", "a", "dict"]
        assert (
            _load(sentinel, {"loading_from_file": True, "source_dir": tmp_path})
            is sentinel
        )

    def test_empty_context_passes_through(self):
        data = {"name": "My Tool"}
        assert _load(data, {}) is data

    def test_copy_on_write_does_not_mutate_input(self, tmp_path):
        (tmp_path / FILENAME).write_text(CODE, encoding="utf-8")
        data = {"name": "My Tool"}
        result = _load(data, {"loading_from_file": True, "source_dir": tmp_path})
        assert "code" not in data  # caller's dict untouched
        assert result is not data
        assert result["code"] == CODE


class TestWriteCodeToSiblingFile:
    def test_writes_file_and_pops_code_under_save_context(self, tmp_path):
        data = {"name": "My Tool", "code": CODE}
        result = _save(data, {"save_attachments": True, "dest_path": tmp_path})
        assert (tmp_path / FILENAME).read_text(encoding="utf-8") == CODE
        assert "code" not in result
        assert result["name"] == "My Tool"

    def test_writes_code_verbatim(self, tmp_path):
        weird = "def run():\n\treturn 'é中'  # unicode + tab\n"
        _save(
            {"code": weird},
            {"save_attachments": True, "dest_path": tmp_path},
            code=weird,
        )
        assert (tmp_path / FILENAME).read_text(encoding="utf-8") == weird

    def test_no_op_without_save_context(self, tmp_path):
        data = {"name": "My Tool", "code": CODE}
        result = _save(data, {})
        assert result == data
        assert result is data  # unchanged object, no copy made
        assert not (tmp_path / FILENAME).exists()

    def test_no_op_without_dest_path(self, tmp_path):
        data = {"code": CODE}
        result = _save(data, {"save_attachments": True})
        assert "code" in result
        assert not (tmp_path / FILENAME).exists()

    def test_non_directory_dest_path_errors(self, tmp_path):
        not_a_dir = tmp_path / "does_not_exist"
        with pytest.raises(ValueError, match="dest_path must be an existing directory"):
            _save({"code": CODE}, {"save_attachments": True, "dest_path": not_a_dir})

    def test_file_dest_path_errors(self, tmp_path):
        # A path that exists but is a file (not a directory) also fails.
        a_file = tmp_path / "afile"
        a_file.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError, match="dest_path must be an existing directory"):
            _save({"code": CODE}, {"save_attachments": True, "dest_path": a_file})

    def test_copy_on_write_does_not_mutate_input(self, tmp_path):
        data = {"name": "My Tool", "code": CODE}
        result = _save(data, {"save_attachments": True, "dest_path": tmp_path})
        assert "code" in data  # caller's dict untouched
        assert result is not data
        assert "code" not in result

    def test_preserves_key_order(self, tmp_path):
        data = {"type": "code_eval", "code": CODE, "reference_keys": ["g"], "z": 1}
        result = _save(data, {"save_attachments": True, "dest_path": tmp_path})
        assert list(result.keys()) == ["type", "reference_keys", "z"]


class TestBareFilenameGuard:
    @pytest.mark.parametrize(
        "bad",
        ["../escape.py", "sub/dir.py", "/abs/tool.py", "a\\b.py", "..\\up.py", ""],
    )
    def test_rejects_non_bare_filenames_on_read(self, tmp_path, bad):
        with pytest.raises(ValueError, match="must be a bare filename"):
            read_code_from_sibling_file(
                {"name": "x"},
                {"loading_from_file": True, "source_dir": tmp_path},
                filename=bad,
                kiln_filename=KILN_FILENAME,
                model_label=MODEL_LABEL,
            )

    @pytest.mark.parametrize(
        "bad",
        ["../escape.py", "sub/dir.py", "/abs/tool.py", "a\\b.py", "..\\up.py", ""],
    )
    def test_rejects_non_bare_filenames_on_write(self, tmp_path, bad):
        with pytest.raises(ValueError, match="must be a bare filename"):
            write_code_to_sibling_file(
                {"code": CODE},
                {"save_attachments": True, "dest_path": tmp_path},
                filename=bad,
                code=CODE,
            )

    def test_accepts_bare_filename(self):
        # Sanity: the module constants used in production pass the guard.
        _require_bare_filename("tool.py")
        _require_bare_filename("scorer.py")

    def test_guard_runs_before_containment_relevant_io(self, tmp_path):
        # Even when a bad filename would resolve to a real writable path, the
        # guard rejects it before any file write happens.
        target_dir = tmp_path / "sub"
        target_dir.mkdir()
        with pytest.raises(ValueError, match="must be a bare filename"):
            write_code_to_sibling_file(
                {"code": CODE},
                {"save_attachments": True, "dest_path": tmp_path},
                filename="sub/x.py",
                code=CODE,
            )
        assert not (target_dir / "x.py").exists()


def test_read_write_round_trip_with_scorer_names(tmp_path):
    # The helper is filename-parameterized; exercise it with the eval caller's
    # constants too so both callers' message/filename wiring is covered here.
    scorer = "scorer.py"
    saved = write_code_to_sibling_file(
        {"type": "code_eval", "code": CODE},
        {"save_attachments": True, "dest_path": tmp_path},
        filename=scorer,
        code=CODE,
    )
    assert "code" not in saved
    assert (tmp_path / scorer).read_text(encoding="utf-8") == CODE

    loaded = read_code_from_sibling_file(
        {"type": "code_eval"},
        {"loading_from_file": True, "source_dir": tmp_path},
        filename=scorer,
        kiln_filename="eval_config.kiln",
        model_label="CodeEvalProperties",
    )
    assert loaded["code"] == CODE


class TestByteForBytePreservation:
    """Binary I/O must preserve exact bytes incl. line endings (functional spec
    §1.1 / §2.1) — no universal-newline translation on read or write."""

    @pytest.mark.parametrize(
        "code",
        [
            "a\r\nb\r\n",  # CRLF
            "a\r\nb\nc\r",  # mixed CRLF / LF / bare CR
            "a\rb\r",  # bare CR only
            "no_trailing_newline",
        ],
    )
    def test_save_writes_exact_bytes(self, tmp_path, code):
        _save(
            {"code": code}, {"save_attachments": True, "dest_path": tmp_path}, code=code
        )
        assert (tmp_path / FILENAME).read_bytes() == code.encode("utf-8")

    @pytest.mark.parametrize(
        "code",
        ["a\r\nb\r\n", "a\r\nb\nc\r", "a\rb\r"],
    )
    def test_load_reconstructs_identical_string(self, tmp_path, code):
        (tmp_path / FILENAME).write_bytes(code.encode("utf-8"))
        loaded = _load(
            {"name": "x"}, {"loading_from_file": True, "source_dir": tmp_path}
        )
        assert loaded["code"] == code

    @pytest.mark.parametrize(
        "code",
        ["a\r\nb\r\n", "a\r\nb\nc\r"],
    )
    def test_save_is_byte_idempotent(self, tmp_path, code):
        _save(
            {"code": code}, {"save_attachments": True, "dest_path": tmp_path}, code=code
        )
        first = (tmp_path / FILENAME).read_bytes()

        # Load reconstructs the string, then a re-save must produce identical bytes.
        loaded = _load(
            {"name": "x"}, {"loading_from_file": True, "source_dir": tmp_path}
        )
        _save(
            {"code": loaded["code"]},
            {"save_attachments": True, "dest_path": tmp_path},
            code=loaded["code"],
        )
        assert (tmp_path / FILENAME).read_bytes() == first == code.encode("utf-8")

    def test_non_utf8_file_raises_unicode_error_on_load(self, tmp_path):
        # A non-UTF-8 sibling file still surfaces UnicodeDecodeError (not newly
        # swallowed, and not converted to the missing-file ValueError).
        (tmp_path / FILENAME).write_bytes(b"\xff\xfe not utf-8")
        with pytest.raises(UnicodeDecodeError):
            _load({"name": "x"}, {"loading_from_file": True, "source_dir": tmp_path})
