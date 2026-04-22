from pathlib import Path
from unittest.mock import Mock, patch

import kiln_ai.pytest_test_output as pytest_test_output
from kiln_ai.pytest_test_output import make_test_output_dir


def test_test_output_root():
    root = pytest_test_output.test_output_root()
    assert isinstance(root, Path)
    assert root.name == "test_output"


def test_make_test_output_dir_basic(tmp_path):
    with patch("kiln_ai.pytest_test_output.test_output_root", lambda: tmp_path):
        request = Mock()
        request.node.name = "test_example"
        request.node.callspec = None

        out_dir = make_test_output_dir(request)
    assert out_dir.exists()
    assert out_dir.is_dir()
    assert "test_example" in str(out_dir)
    assert "default" in str(out_dir)


def test_make_test_output_dir_with_param_id(tmp_path):
    with patch("kiln_ai.pytest_test_output.test_output_root", lambda: tmp_path):
        request = Mock()
        request.node.name = "test_param[case1]"
        request.node.callspec.id = "my-param"

        out_dir = make_test_output_dir(request)
    assert out_dir.exists()
    assert "my-param" in str(out_dir)


def test_make_test_output_dir_sanitizes_names(tmp_path):
    with patch("kiln_ai.pytest_test_output.test_output_root", lambda: tmp_path):
        request = Mock()
        request.node.name = "test_with spaces/and:special!chars"
        request.node.callspec.id = "param with spaces"

        out_dir = make_test_output_dir(request)
    assert out_dir.exists()
    # Special chars replaced with underscores
    assert " " not in out_dir.parts[-3]
    assert "/" not in out_dir.parts[-3]


def test_make_test_output_dir_node_without_callspec(tmp_path):
    with patch("kiln_ai.pytest_test_output.test_output_root", lambda: tmp_path):

        class NodeWithoutCallspec:
            name = "test_no_callspec"

        request = Mock()
        request.node = NodeWithoutCallspec()

        out_dir = make_test_output_dir(request)
    assert out_dir.exists()
    assert "default" in str(out_dir)


def test_make_test_output_dir_callspec_without_id(tmp_path):
    with patch("kiln_ai.pytest_test_output.test_output_root", lambda: tmp_path):
        callspec = Mock()
        callspec.id = None

        request = Mock()
        request.node.name = "test_param[case1]"
        request.node.callspec = callspec

        out_dir = make_test_output_dir(request)
    assert out_dir.exists()
    assert "default" in str(out_dir)
