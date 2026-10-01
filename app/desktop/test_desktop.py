import os
import random
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
from uvicorn import Config as UvicornConfig

import app.desktop.desktop_server as desktop_server
from app.desktop.desktop import DesktopApp, DesktopServer

TEST_PORT = 8123
UNPATCHED_START_LINUX_SNI_TRAY = DesktopApp.start_linux_sni_tray


@pytest.fixture(autouse=True)
def mock_gui_modules():
    """Mock GUI modules globally to prevent display errors in headless CI."""
    with patch("app.desktop.desktop.tk.Tk"):
        yield


@pytest.fixture(autouse=True)
def mock_linux_sni_tray():
    """Keep tests off the real session bus; by default the SNI tray is unavailable."""
    with patch.object(
        DesktopApp, "start_linux_sni_tray", return_value=None
    ) as mock_start:
        yield mock_start


@pytest.fixture
def mock_tk_root():
    """Mock tkinter root window."""
    with patch("app.desktop.desktop.tk.Tk") as mock_tk:
        mock_root = Mock()
        mock_tk.return_value = mock_root
        yield mock_root


@pytest.fixture
def mock_image():
    """Mock PIL Image."""
    with patch("app.desktop.desktop.Image") as mock_img:
        mock_image_obj = Mock()
        mock_img.open.return_value = mock_image_obj
        yield mock_image_obj


@pytest.fixture
def mock_kiln_tray():
    """Mock KilnTray."""
    with patch("app.desktop.desktop.KilnTray") as mock_tray_class:
        mock_tray = Mock()
        mock_tray_class.return_value = mock_tray
        yield mock_tray


@pytest.fixture
def mock_webbrowser():
    """Mock webbrowser module."""
    with patch("app.desktop.desktop.webbrowser") as mock_wb:
        yield mock_wb


@pytest.fixture
def mock_kiln_menu_item():
    """Mock pystray module."""
    with patch("app.desktop.desktop.KilnMenuItem") as mock_menu_item:
        yield mock_menu_item


class TestDesktopApp:
    """Test the DesktopApp class."""

    def test_init(self, mock_tk_root):
        """Test DesktopApp initialization."""
        app = DesktopApp(port=TEST_PORT)

        assert app.root == mock_tk_root
        assert app.tray is None
        mock_tk_root.title.assert_called_once_with("Kiln")
        mock_tk_root.withdraw.assert_called_once()

    def test_start(self, mock_tk_root, mock_kiln_tray):
        """Test app start method."""
        app = DesktopApp(port=TEST_PORT)

        # Mock the mainloop to prevent hanging
        mock_tk_root.mainloop = Mock()

        with patch.object(app, "run_tray") as mock_run_tray:
            app.start()

            # Verify dock callback is registered
            mock_tk_root.createcommand.assert_called_once()
            command_name, _ = mock_tk_root.createcommand.call_args[0]
            assert command_name == "tk::mac::ReopenApplication"

            # Verify tray is started
            mock_run_tray.assert_called_once()

            # Verify scheduled callbacks
            assert mock_tk_root.after.call_count == 2
            after_calls = mock_tk_root.after.call_args_list
            assert after_calls[0][0] == (200, app.show_studio)
            assert after_calls[1][0] == (200, app.close_splash)

            # Verify mainloop is called
            mock_tk_root.mainloop.assert_called_once()

    def test_quit_app_with_tray_and_root(self, mock_tk_root, mock_kiln_tray):
        """Test quit_app when both tray and root exist."""
        app = DesktopApp(port=TEST_PORT)
        app.tray = mock_kiln_tray

        app.quit_app()

        mock_kiln_tray.stop.assert_called_once()
        mock_tk_root.destroy.assert_called_once()

    def test_quit_app_no_tray(self, mock_tk_root):
        """Test quit_app when tray is None."""
        app = DesktopApp(port=TEST_PORT)
        app.tray = None

        app.quit_app()

        # Should still call root.destroy
        mock_tk_root.destroy.assert_called_once()

    def test_on_quit_with_root(self, mock_tk_root):
        """Test on_quit when root exists."""
        app = DesktopApp(port=TEST_PORT)

        with patch.object(app, "quit_app") as mock_quit_app:
            app.on_quit()

            # Should schedule quit_app via tk.after
            mock_tk_root.after.assert_called_once_with(100, mock_quit_app)

    def test_on_quit_without_root(self, mock_tk_root):
        """Test on_quit when root is None."""
        app = DesktopApp(port=TEST_PORT)

        with patch.object(app, "quit_app") as mock_quit_app:
            with patch.object(app, "root", None):
                app.on_quit()

                # Should call quit_app directly
                mock_quit_app.assert_called_once()

    def test_show_studio(self, mock_tk_root, mock_webbrowser):
        """Test show_studio opens the correct URL."""
        app = DesktopApp(port=TEST_PORT)

        app.show_studio()

        mock_webbrowser.open.assert_called_once_with(f"http://localhost:{TEST_PORT}")

    def test_resource_path_with_meipass(self, mock_tk_root):
        """Test resource_path when running from PyInstaller bundle."""
        app = DesktopApp(port=TEST_PORT)

        with patch.object(sys, "_MEIPASS", "/bundled/path", create=True):
            result = app.resource_path("icon.png")

            expected = os.path.join("/bundled/path", "icon.png")
            assert result == expected

    def test_resource_path_without_meipass(self, mock_tk_root):
        """Test resource_path when running from source."""
        app = DesktopApp(port=TEST_PORT)

        # Ensure _MEIPASS doesn't exist
        if hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")

        result = app.resource_path("icon.png")

        # Since we're testing, it will use the test file's directory
        assert result.endswith("icon.png")

    def test_run_tray_first_time(
        self, mock_tk_root, mock_image, mock_kiln_tray, mock_kiln_menu_item
    ):
        """Test run_tray when tray doesn't exist yet."""
        app = DesktopApp(port=TEST_PORT)

        with patch.object(app, "resource_path", return_value="taskbar.png"):
            app.run_tray()

            # Verify menu items are created
            assert mock_kiln_menu_item.call_count == 2
            menu_calls = mock_kiln_menu_item.call_args_list

            # First menu item (Open Kiln Studio)
            assert menu_calls[0][0][0] == "Open Kiln Studio"
            assert menu_calls[0][0][1] == app.show_studio

            # Second menu item (Quit)
            assert menu_calls[1][0][0] == "Quit"
            assert menu_calls[1][0][1] == app.on_quit

            # Verify tray is created and started
            assert app.tray == mock_kiln_tray
            mock_kiln_tray.run_detached.assert_called_once()

    def test_run_tray_already_exists(self, mock_tk_root, mock_kiln_tray):
        """Test run_tray when tray already exists."""
        app = DesktopApp(port=TEST_PORT)
        app.tray = mock_kiln_tray

        with patch.object(app, "resource_path") as mock_resource_path:
            app.run_tray()

            # Should return early without creating new tray
            mock_resource_path.assert_not_called()

    @patch("app.desktop.desktop.sys.platform", "win32")
    def test_run_tray_windows_default(
        self, mock_tk_root, mock_image, mock_kiln_tray, mock_kiln_menu_item
    ):
        """Test run_tray sets default=True on Windows."""
        app = DesktopApp(port=TEST_PORT)

        with patch.object(app, "resource_path", return_value="taskbar.png"):
            app.run_tray()

            # Check first menu item has default=True
            menu_calls = mock_kiln_menu_item.call_args_list
            assert menu_calls[0][1]["default"] is True

    @patch("app.desktop.desktop.sys.platform", "darwin")
    def test_run_tray_macos_no_default(
        self, mock_tk_root, mock_image, mock_kiln_tray, mock_kiln_menu_item
    ):
        """Test run_tray sets default=False on macOS."""
        app = DesktopApp(port=TEST_PORT)

        with patch.object(app, "resource_path", return_value="taskbar.png"):
            app.run_tray()

            # Check first menu item has default=False
            menu_calls = mock_kiln_menu_item.call_args_list
            assert menu_calls[0][1]["default"] is False

    @patch("app.desktop.desktop.sys.platform", "linux")
    def test_run_tray_linux_uses_sni_tray_when_available(
        self, mock_tk_root, mock_linux_sni_tray
    ):
        sni_tray = Mock()
        mock_linux_sni_tray.return_value = sni_tray
        app = DesktopApp(port=TEST_PORT)

        with patch("app.desktop.desktop.KilnTray") as kiln_tray_class:
            app.run_tray()

        assert app.tray is sni_tray
        kiln_tray_class.assert_not_called()

    @patch("app.desktop.desktop.sys.platform", "linux")
    def test_run_tray_linux_falls_back_to_pystray(
        self,
        mock_tk_root,
        mock_image,
        mock_kiln_tray,
        mock_kiln_menu_item,
        mock_linux_sni_tray,
    ):
        app = DesktopApp(port=TEST_PORT)

        with patch.object(app, "resource_path", return_value="taskbar.png"):
            app.run_tray()

        mock_linux_sni_tray.assert_called_once()
        assert app.tray == mock_kiln_tray
        mock_kiln_tray.run_detached.assert_called_once()

    @pytest.mark.parametrize("platform", ["darwin", "win32"])
    def test_run_tray_other_platforms_skip_sni_tray(
        self,
        mock_tk_root,
        mock_image,
        mock_kiln_tray,
        mock_kiln_menu_item,
        mock_linux_sni_tray,
        platform,
    ):
        app = DesktopApp(port=TEST_PORT)

        with (
            patch("app.desktop.desktop.sys.platform", platform),
            patch.object(app, "resource_path", return_value="taskbar.png"),
        ):
            app.run_tray()

        mock_linux_sni_tray.assert_not_called()
        assert app.tray == mock_kiln_tray

    @patch("app.desktop.desktop.sys.platform", "linux")
    def test_run_tray_linux_pystray_failure_is_not_fatal(
        self, mock_tk_root, mock_image, mock_kiln_tray, mock_kiln_menu_item
    ):
        mock_kiln_tray.run_detached.side_effect = RuntimeError("no tray")
        app = DesktopApp(port=TEST_PORT)

        with patch.object(app, "resource_path", return_value="taskbar.png"):
            app.run_tray()

        assert app.tray is None

    @pytest.mark.skipif(sys.platform != "linux", reason="SNI tray module is Linux-only")
    def test_start_linux_sni_tray_passes_menu_and_icons(self, mock_tk_root):
        app = DesktopApp(port=TEST_PORT)
        mock_start = Mock()

        with (
            patch("app.desktop.linux_tray.sni_tray.start_sni_tray", mock_start),
            patch.object(app, "show_studio") as show_studio,
            patch.object(app, "on_quit") as on_quit,
        ):
            assert UNPATCHED_START_LINUX_SNI_TRAY(app) is mock_start.return_value
            kwargs = mock_start.call_args.kwargs
            open_item, quit_item = kwargs["menu_items"]
            open_item.on_click()
            quit_item.on_click()

        assert kwargs["title"] == "Kiln"
        assert kwargs["icon_dir"] == Path(app.resource_path("linux_tray/icons"))
        assert kwargs["on_activate"] == show_studio
        assert (open_item.label, quit_item.label) == ("Open Kiln Studio", "Quit")
        show_studio.assert_called_once()
        on_quit.assert_called_once()

    def test_start_linux_sni_tray_never_raises(self, mock_tk_root):
        app = DesktopApp(port=TEST_PORT)

        with patch.dict(sys.modules, {"app.desktop.linux_tray.sni_tray": None}):
            assert UNPATCHED_START_LINUX_SNI_TRAY(app) is None

    def test_linux_tray_icon_dir_is_bundled(self):
        build_script = (Path(__file__).parent / "build_desktop_app.sh").read_text()
        icon_dir = Path(__file__).parent / "linux_tray" / "icons"

        assert "--add-data ../linux_tray/icons:./linux_tray/icons" in build_script
        assert (icon_dir / "kiln-symbolic.svg").is_file()

    def test_close_splash_with_pyi_splash(self, mock_tk_root):
        """Test close_splash when pyi_splash is available."""
        app = DesktopApp(port=TEST_PORT)

        mock_pyi_splash = Mock()
        with patch.dict("sys.modules", {"pyi_splash": mock_pyi_splash}):
            app.close_splash()

            mock_pyi_splash.close.assert_called_once()

    def test_close_splash_without_pyi_splash(self, mock_tk_root):
        """Test close_splash when pyi_splash is not available."""
        app = DesktopApp(port=TEST_PORT)

        # Should not raise an exception
        app.close_splash()


class TestDesktopServer:
    """Test the DesktopServer class."""

    def test_init(self, mock_tk_root):
        """Test DesktopServer initialization."""
        app = DesktopApp(port=TEST_PORT)
        config = Mock(spec=UvicornConfig)

        server = DesktopServer(app, config)

        assert server.app == app
        assert server.config == config

    def test_run_in_thread_calls_app_on_quit(self, mock_tk_root):
        """Test that run_in_thread calls app.on_quit when context exits."""
        app = DesktopApp(port=TEST_PORT)
        config = Mock(spec=UvicornConfig)
        server = DesktopServer(app, config)

        with patch.object(app, "on_quit") as mock_on_quit:
            with patch(
                "app.desktop.desktop.ThreadedServer.run_in_thread"
            ) as mock_super_run:
                # Mock the super context manager
                mock_context = Mock()
                mock_super_run.return_value.__enter__ = Mock(return_value=mock_context)
                mock_super_run.return_value.__exit__ = Mock(return_value=None)

                with server.run_in_thread():
                    pass

                mock_on_quit.assert_called_once()


def test_desktop_app_server():
    """Test the desktop app server integration (existing test)."""
    # random port between 9000 and 12000
    port = random.randint(9000, 12000)
    config = desktop_server.server_config(port=port, host="127.0.0.1")
    uni_server = desktop_server.ThreadedServer(config=config)
    with uni_server.run_in_thread():
        r = requests.get("http://127.0.0.1:{}/ping".format(port))
        assert r.status_code == 200
