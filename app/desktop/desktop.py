import contextlib
import os
import sys
import tkinter as tk
import webbrowser

import pystray
from PIL import Image

from app.desktop.custom_tray import KilnTray
from app.desktop.desktop_server import ThreadedServer, server_config

# TODO: remove this and all other globals in this file
root = None  # type: tk.Tk | None
tray = None  # type: ignore


class DesktopServer(ThreadedServer):
    @contextlib.contextmanager
    def run_in_thread(self):
        try:
            with super().run_in_thread():
                yield
        finally:
            on_quit()


def show_studio():
    webbrowser.open("http://localhost:8757")


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # type: ignore
    except Exception:
        base_path = os.path.dirname(__file__)

    return os.path.join(base_path, relative_path)


def quit_app():
    # TODO: Windows issue needs pyinstaller update: https://github.com/pyinstaller/pyinstaller/issues/8701
    global tray
    if tray is not None:
        tray.stop()
    global root
    if root is not None:
        root.destroy()
        # TODO: shouldn't need explicit exit, but would need to test all platforms to remove
        sys.exit(0)


def on_quit():
    global root
    # use main runloop if possible
    if root:
        root.after(100, quit_app)
    else:
        quit_app()


def run_taskbar():
    image = Image.open(resource_path("taskbar.png"))
    # Use default on Windows to get "left click to open" behaviour. But it looks ugle on MacOS, so don't use it there
    make_open_studio_default = sys.platform == "Windows"
    menu = (
        pystray.MenuItem(
            "Open Kiln Studio", show_studio, default=make_open_studio_default
        ),
        pystray.MenuItem("Quit", on_quit),
    )
    global tray
    tray = KilnTray("kiln", image, "Kiln", menu)
    # running detached since we use tk mainloop to get events from dock icon
    tray.run_detached()
    return tray


def close_splash():
    try:
        import pyi_splash  # type: ignore

        pyi_splash.close()
    except ModuleNotFoundError:
        pass


if __name__ == "__main__":
    # run the server in a thread, and shut down server when main thread exits
    # use_colors=False to disable colored logs, as windows doesn't support them
    config = server_config()
    uni_server = DesktopServer(config=config)
    with uni_server.run_in_thread():
        if not uni_server.running():
            # Can't start. Likely a port is already in use. Show the web app instead and exit
            show_studio()
            on_quit()
        # TK without a window, to get dock events on MacOS
        root = tk.Tk()
        root.title("kiln")
        root.withdraw()  # remove the window
        # Register callback for the dock icon to reopen the web app
        root.createcommand("tk::mac::ReopenApplication", show_studio)
        tray = run_taskbar()
        root.after(10, show_studio)
        root.after(10, close_splash)
        root.mainloop()
