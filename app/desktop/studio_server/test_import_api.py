import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop.studio_server.import_api import _show_file_dialog, connect_import_api


@pytest.fixture
def app():
    app = FastAPI()
    return app


@pytest.fixture
def client_no_tk(app):
    connect_import_api(app, tk_root=None)
    return TestClient(app)


@pytest.fixture
def mock_tk_root():
    mock_root = MagicMock(spec=tk.Tk)
    return mock_root


@pytest.fixture
def client_with_tk(app, mock_tk_root):
    connect_import_api(app, tk_root=mock_tk_root)
    return TestClient(app)


def test_select_kiln_file_no_tk_root(client_no_tk):
    """Test that the endpoint raises HTTPException when tk_root is None"""
    response = client_no_tk.get("/api/select_kiln_file")
    assert response.status_code == 400
    assert "Not running in app mode" in response.json()["detail"]


def test_select_kiln_file_with_custom_title(client_no_tk):
    """Test that custom title parameter is handled when tk_root is None"""
    response = client_no_tk.get("/api/select_kiln_file?title=Custom Title")
    assert response.status_code == 400
    assert "Not running in app mode" in response.json()["detail"]


@patch("app.desktop.studio_server.import_api.filedialog.askopenfilename")
def test_select_kiln_file_success(mock_filedialog, client_with_tk, mock_tk_root):
    """Test successful file selection"""
    mock_filedialog.return_value = "/path/to/test.kiln"

    response = client_with_tk.get("/api/select_kiln_file")

    assert response.status_code == 200
    assert response.json() == {"file_path": "/path/to/test.kiln"}

    # Verify dialog was called with correct parameters
    mock_filedialog.assert_called_once_with(
        parent=mock_tk_root,
        title="Select Kiln File",
        filetypes=[("Kiln files", "*.kiln"), ("All files", "*.*")],
    )


@patch("app.desktop.studio_server.import_api.filedialog.askopenfilename")
def test_select_kiln_file_with_custom_title_success(
    mock_filedialog, client_with_tk, mock_tk_root
):
    """Test successful file selection with custom title"""
    mock_filedialog.return_value = "/path/to/custom.kiln"

    response = client_with_tk.get("/api/select_kiln_file?title=Choose Your File")

    assert response.status_code == 200
    assert response.json() == {"file_path": "/path/to/custom.kiln"}

    # Verify dialog was called with custom title
    mock_filedialog.assert_called_once_with(
        parent=mock_tk_root,
        title="Choose Your File",
        filetypes=[("Kiln files", "*.kiln"), ("All files", "*.*")],
    )


@patch("app.desktop.studio_server.import_api.filedialog.askopenfilename")
def test_select_kiln_file_cancelled(mock_filedialog, client_with_tk):
    """Test when user cancels file selection (returns empty string)"""
    mock_filedialog.return_value = ""

    response = client_with_tk.get("/api/select_kiln_file")

    assert response.status_code == 200
    assert response.json() == {"file_path": None}


@patch("app.desktop.studio_server.import_api.filedialog.askopenfilename")
def test_show_file_dialog_window_manipulation(mock_filedialog):
    """Test that _show_file_dialog properly manipulates the tkinter window"""
    mock_root = MagicMock(spec=tk.Tk)
    mock_filedialog.return_value = "/test/path.kiln"

    result = _show_file_dialog(mock_root, "Test Title")

    # Verify window manipulation calls
    mock_root.deiconify.assert_called_once()
    mock_root.lift.assert_called_once()
    mock_root.attributes.assert_any_call("-topmost", True)
    mock_root.attributes.assert_any_call("-topmost", False)
    mock_root.update_idletasks.assert_called_once()
    mock_root.focus_force.assert_called_once()
    mock_root.withdraw.assert_called_once()

    # Verify filedialog was called correctly
    mock_filedialog.assert_called_once_with(
        parent=mock_root,
        title="Test Title",
        filetypes=[("Kiln files", "*.kiln"), ("All files", "*.*")],
    )

    assert result == "/test/path.kiln"
