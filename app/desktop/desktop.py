# ruff: noqa: E402
from app.desktop.studio_server.setup_certs import setup_certs  # isort:skip

# setup_certs must run before imports to register root certs
setup_certs()

import contextlib
import os
import sys
import tkinter as tk
import webbrowser

import pystray
from PIL import Image

# Unused, but needed for pyinstaller to not miss this import
from pydantic.deprecated.decorator import deprecated  # noqa # type: ignore
from uvicorn import Config as UvicornConfig

from app.desktop.custom_tray import KilnTray
from app.desktop.desktop_server import ThreadedServer, server_config


class DesktopApp:
    def __init__(self):
        # TK without a window, to get dock events on MacOS
        self.root = tk.Tk()
        self.root.title("Kiln")
        self.root.withdraw()
        self.tray: KilnTray | None = None

    def start(self):
        """
        Start the desktop app, showing the web app, tray, and closing the splash screen.
        """

        # Register a callback for the dock icon (MacOS) to reopen the web app
        def _show_studio():
            self.show_studio()

        self.root.createcommand("tk::mac::ReopenApplication", _show_studio)

        # Run the tray
        self.run_tray()

        # Show the web app after a short delay, to avoid race with the server starting
        self.root.after(200, self.show_studio)
        self.root.after(200, self.close_splash)

        # Run the main loop until the app is quit (quit menu item usually)
        self.root.mainloop()

    def quit_app(self):
        """
        Shutdown the app (taskbar, and desktop tk app)
        """

        if self.tray is not None:
            self.tray.stop()
        if self.root is not None:
            self.root.destroy()

    def on_quit(self):
        """
        Quit event handler. Will dipatch the shutdown to the most appropriate place (main loop ideally)
        """

        # use tk mainloop if possible
        if self.root:
            self.root.after(100, self.quit_app)
        else:
            self.quit_app()

    def show_studio(self):
        """
        Open the web app in the default browser.
        """

        webbrowser.open("http://localhost:8757")

    def resource_path(self, relative_path):
        """
        Get the path to the resource files (webapp, taskbar icon, etc)
        """

        try:
            base_path = sys._MEIPASS  # type: ignore
        except Exception:
            base_path = os.path.dirname(__file__)

        return os.path.join(base_path, relative_path)

    def run_tray(self):
        """
        Run the tray with menu items for quit and open studio.
        """

        if self.tray is not None:
            return

        tray_image = Image.open(self.resource_path("taskbar.png"))

        # Use default on Windows to get "left click to open" behaviour. But it looks ugle on MacOS, so don't use it there
        make_open_studio_default = sys.platform == "Windows"

        menu = (
            pystray.MenuItem(
                "Open Kiln Studio", self.show_studio, default=make_open_studio_default
            ),
            pystray.MenuItem("Quit", self.on_quit),
        )

        self.tray = KilnTray("kiln", tray_image, "Kiln", menu)

        # running detached since we use tk mainloop to get events from dock icon
        self.tray.run_detached()

    def close_splash(self):
        try:
            import pyi_splash  # type: ignore

            pyi_splash.close()
        except ModuleNotFoundError:
            pass


class DesktopServer(ThreadedServer):
    """
    A wrapper around the threaded app server which runs in a thread, but also shuts down the app when the server stops.
    """

    def __init__(self, app: DesktopApp, config: UvicornConfig):
        self.app = app
        super().__init__(config=config)

    @contextlib.contextmanager
    def run_in_thread(self):
        try:
            with super().run_in_thread():
                yield
        finally:
            self.app.on_quit()


if __name__ == "__main__":
    app = DesktopApp()

    # Create and run the server
    # run the server in a thread, and shut down server when main thread (tk mainloop) exits
    config = server_config(tk_root=app.root)
    uni_server = DesktopServer(app=app, config=config)
    with uni_server.run_in_thread():
        if not uni_server.running():
            # Can't start. Likely the port is already in use (app already running). Show the existing web app and exit.
            app.show_studio()
            app.on_quit()

        # start the desktop app once the server is running. It will keep running until the tk mainloop exits (quit menu item usually)
        app.start()
