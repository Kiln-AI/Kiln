"""Linux tray icon experiments. Throwaway: selected by CLI flags, see REPORT.md.

Flags (all optional; without them the tray behaves exactly as before):

  --tray-variant <name>      which icon / icon mechanism to use (VARIANTS below)
  --tray-backend <name>      appindicator | gtk | xorg; sets PYSTRAY_BACKEND before
                             pystray is imported
  --tray-size <px>           size of the PNG handed to pystray (default 64 for
                             appindicator/gtk; xorg always uses the exact slot size)
  --tray-xorg <mode>         how the xorg (XEmbed) backend paints:
                               stock    pystray as-is (alpha dropped onto black)
                               argb     32-bit window using _NET_SYSTEM_TRAY_VISUAL
                               pseudo   ParentRelative background, read back, composite
                               bg:#hex  pre-composite onto a fixed color
                               bg:auto  pre-composite onto dark/light guess (mono-auto)
  --tray-glib-thread on|off  run a GLib main loop thread for gtk/appindicator
                             (default on; off reproduces current production)
  --tray-exit-after <sec>    quit the app after N seconds (for scripted screenshots)

Logs go to stderr and to $KILN_TRAY_LOG (default /tmp/kiln-tray-experiments.log).

pystray is pinned to 0.19.5 for this module: we subclass private classes
(pystray._appindicator.Icon, pystray._xorg.Icon) and override private methods.
"""

import argparse
import importlib
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image

log = logging.getLogger("kiln.tray")

VARIANTS = [
    "baseline",
    "pr1814",
    "color",
    "tile",
    "mono-white",
    "mono-black",
    "mono-white-edge",
    "mono-black-edge",
    "mono-auto",
    "symbolic",
    "themed",
]
ASSET_VARIANTS = {
    "color",
    "tile",
    "mono-white",
    "mono-black",
    "mono-white-edge",
    "mono-black-edge",
}
BACKENDS = ["appindicator", "gtk", "xorg", "sni"]
PR1814_BG = (68, 70, 60, 255)
DARK_PANEL_GUESS = (0x1D, 0x1D, 0x1D)
LIGHT_PANEL_GUESS = (0xF6, 0xF5, 0xF4)


@dataclass
class TrayOptions:
    variant: str | None = None
    backend: str | None = None
    size: int | None = None
    xorg: str = "stock"
    glib_thread: bool = True
    exit_after: float | None = None

    @property
    def any_set(self) -> bool:
        return bool(self.variant or self.backend or self.size or self.xorg != "stock")


OPTIONS = TrayOptions()
_pystray_import_error: BaseException | None = None


# ------------------------------------------------------------------ early init


def _setup_logger() -> None:
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    log.propagate = False
    fmt = logging.Formatter("%(asctime)s [tray] %(message)s")
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(fmt)
    log.addHandler(h)
    path = os.environ.get("KILN_TRAY_LOG", "/tmp/kiln-tray-experiments.log")
    try:
        fh = logging.FileHandler(path)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass


def early_init(argv: list[str] | None = None) -> TrayOptions:
    """Parse and strip our flags, set PYSTRAY_BACKEND. Must run before pystray import."""
    argv = sys.argv if argv is None else argv
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--tray-variant", choices=VARIANTS)
    p.add_argument("--tray-backend", choices=BACKENDS)
    p.add_argument("--tray-size", type=int)
    p.add_argument("--tray-xorg", default="stock")
    p.add_argument("--tray-glib-thread", choices=["on", "off"], default="on")
    p.add_argument("--tray-exit-after", type=float)
    args, rest = p.parse_known_args(argv[1:])
    argv[1:] = rest

    OPTIONS.variant = args.tray_variant
    OPTIONS.backend = args.tray_backend
    OPTIONS.size = args.tray_size
    OPTIONS.xorg = args.tray_xorg
    OPTIONS.glib_thread = args.tray_glib_thread == "on"
    OPTIONS.exit_after = args.tray_exit_after

    if not sys.platform.startswith("linux"):
        return OPTIONS

    _setup_logger()
    if OPTIONS.backend and OPTIONS.backend != "sni":
        os.environ["PYSTRAY_BACKEND"] = OPTIONS.backend
    log.info("options: %s", OPTIONS)
    log_environment()
    return OPTIONS


def record_pystray_import_error(e: BaseException) -> None:
    global _pystray_import_error
    _pystray_import_error = e


def _run(cmd: list[str], timeout: float = 3) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr).strip()
    except Exception as e:
        return f"error: {e}"


def _probe_gi() -> None:
    try:
        import gi

        log.info("gi: OK version=%s file=%s", gi.__version__, gi.__file__)
    except Exception as e:
        log.info("gi: FAILED %r", e)
        return
    for ns, ver in [
        ("Gtk", "3.0"),
        ("AyatanaAppIndicator3", "0.1"),
        ("AppIndicator3", "0.1"),
    ]:
        try:
            gi.require_version(ns, ver)
            importlib.import_module(f"gi.repository.{ns}")
            log.info("gi.repository.%s %s: OK", ns, ver)
        except Exception as e:
            log.info("gi.repository.%s %s: FAILED %r", ns, ver, e)


def _probe_dbus() -> None:
    for name in [
        "org.kde.StatusNotifierWatcher",
        "org.freedesktop.Notifications",
        "org.freedesktop.portal.Desktop",
    ]:
        out = _run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.freedesktop.DBus",
                "--object-path",
                "/org/freedesktop/DBus",
                "--method",
                "org.freedesktop.DBus.NameHasOwner",
                name,
            ]
        )
        log.info("dbus %s has owner: %s", name, out)
    out = _run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.kde.StatusNotifierWatcher",
            "--object-path",
            "/StatusNotifierWatcher",
            "--method",
            "org.freedesktop.DBus.Properties.Get",
            "org.kde.StatusNotifierWatcher",
            "IsStatusNotifierHostRegistered",
        ]
    )
    log.info("StatusNotifierWatcher.IsStatusNotifierHostRegistered: %s", out)


def _probe_xembed() -> None:
    if not os.environ.get("DISPLAY"):
        log.info("xembed: no DISPLAY")
        return
    try:
        import Xlib.display
        import Xlib.X
        import Xlib.Xatom

        d = Xlib.display.Display()
        screen = d.screen()
        sel = d.intern_atom(f"_NET_SYSTEM_TRAY_S{d.get_default_screen()}")
        owner = d.get_selection_owner(sel)
        if owner == Xlib.X.NONE:
            log.info("xembed: no tray manager owns %s", "_NET_SYSTEM_TRAY_S0")
            d.close()
            return
        prop = owner.get_full_property(
            d.intern_atom("_NET_SYSTEM_TRAY_VISUAL"), Xlib.Xatom.VISUALID
        )
        vid = prop.value[0] if prop else None
        depth = None
        for dep in screen.allowed_depths:
            if any(v.visual_id == vid for v in dep.visuals):
                depth = dep.depth
        log.info(
            "xembed: tray manager 0x%x, _NET_SYSTEM_TRAY_VISUAL=%s depth=%s (root depth %s)",
            owner.id,
            hex(vid) if vid else None,
            depth,
            screen.root_depth,
        )
        d.close()
    except Exception as e:
        log.info("xembed probe failed: %r", e)


def log_environment() -> None:
    log.info(
        "frozen=%s _MEIPASS=%s python=%s",
        getattr(sys, "frozen", False),
        getattr(sys, "_MEIPASS", None),
        sys.version.split()[0],
    )
    for k in [
        "XDG_CURRENT_DESKTOP",
        "XDG_SESSION_DESKTOP",
        "DESKTOP_SESSION",
        "XDG_SESSION_TYPE",
        "WAYLAND_DISPLAY",
        "DISPLAY",
        "GDK_BACKEND",
        "PYSTRAY_BACKEND",
        "GI_TYPELIB_PATH",
    ]:
        log.info("env %s=%s", k, os.environ.get(k))
    _probe_gi()
    _probe_dbus()
    _probe_xembed()


def log_backend_report() -> str | None:
    """Log which pystray backend loaded, and why the others didn't."""
    if not sys.platform.startswith("linux"):
        return None
    if _pystray_import_error is not None:
        log.info("pystray import FAILED: %r", _pystray_import_error)
        return None
    import pystray

    chosen = pystray.Icon.__module__.rsplit("._", 1)[-1]
    log.info("pystray backend LOADED: %s (%s)", chosen, pystray.Icon.__module__)
    for name in BACKENDS:
        if name == chosen or name == "sni":
            continue
        try:
            importlib.import_module(f"pystray._{name}")
            log.info("pystray backend %s: importable (not chosen)", name)
        except Exception as e:
            log.info("pystray backend %s: not usable: %r", name, e)
    return chosen


# ------------------------------------------------------------------ assets


def icons_dir(resource_path: Callable[[str], str]) -> Path:
    return Path(resource_path("tray_icons"))


def load_asset(
    resource_path: Callable[[str], str], set_name: str, size: int
) -> Image.Image:
    d = icons_dir(resource_path) / set_name
    exact = d / f"kiln-{size}.png"
    if exact.exists():
        return Image.open(exact).convert("RGBA")
    # nearest larger, premultiplied downscale (Pillow premultiplies RGBA resizes)
    sizes = sorted(int(p.stem.split("-")[1]) for p in d.glob("kiln-*.png"))
    src = next((s for s in sizes if s >= size), sizes[-1])
    im = Image.open(d / f"kiln-{src}.png").convert("RGBA")
    return im.resize((size, size), Image.Resampling.LANCZOS)


def pr1814_image(taskbar: Image.Image) -> Image.Image:
    rgba = taskbar.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, PR1814_BG)
    bg.alpha_composite(rgba)
    return bg.convert("RGB").resize((24, 24), Image.Resampling.LANCZOS)


# ------------------------------------------------------------------ mono-auto


def _portal_color_scheme() -> int | None:
    base = [
        "gdbus",
        "call",
        "--session",
        "--dest",
        "org.freedesktop.portal.Desktop",
        "--object-path",
        "/org/freedesktop/portal/desktop",
        "--method",
    ]
    for method in [
        "org.freedesktop.portal.Settings.ReadOne",
        "org.freedesktop.portal.Settings.Read",
    ]:
        out = _run([*base, method, "org.freedesktop.appearance", "color-scheme"])
        log.info("mono-auto: portal %s -> %s", method.rsplit(".", 1)[-1], out)
        if out:
            m = re.search(r"uint32 (\d+)", out)
            if m:
                return int(m.group(1))
    return None


def _gsettings_color_scheme() -> int | None:
    out = _run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
    log.info("mono-auto: gsettings color-scheme -> %s", out)
    if not out:
        return None
    if "prefer-dark" in out:
        return 1
    if "prefer-light" in out:
        return 2
    return 0


def color_scheme() -> int | None:
    """0/None = no preference or unknown, 1 = dark, 2 = light."""
    scheme = _portal_color_scheme()
    if scheme in (1, 2):
        return scheme
    return _gsettings_color_scheme()


def _xfce_panel_dark() -> tuple[bool, str] | None:
    mode = _run(["xfconf-query", "-c", "xfce4-panel", "-p", "/panels/dark-mode"])
    theme = _run(["xfconf-query", "-c", "xsettings", "-p", "/Net/ThemeName"])
    log.info("mono-auto: xfconf panel dark-mode=%s gtk theme=%s", mode, theme)
    if mode is None and theme is None:
        return None
    if mode == "true":
        return True, "xfce4-panel dark-mode=true"
    if theme and "dark" in theme.lower():
        return True, f"GTK theme {theme} is dark"
    return False, "xfce4-panel dark-mode off and GTK theme not dark"


def decide_panel_is_dark(scheme: int | None = None) -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    parts = [p for p in desktop.split(":") if p]
    if scheme is None:
        scheme = color_scheme()
    log.info("mono-auto: desktop parts=%s color-scheme=%s", parts, scheme)
    if any(p in ("gnome", "unity", "ubuntu", "pop") for p in parts):
        dark, why = True, "GNOME/Unity top bar is always dark"
    elif "cinnamon" in parts:
        dark, why = True, "Cinnamon panel default is dark"
    elif "xfce" in parts and (xfce := _xfce_panel_dark()) is not None:
        dark, why = xfce
    elif scheme == 1:
        dark, why = True, "color-scheme=1 (prefer dark)"
    elif scheme == 2:
        dark, why = False, "color-scheme=2 (prefer light)"
    else:
        dark, why = True, "unknown; default to dark panel"
    log.info("mono-auto: panel dark=%s (%s)", dark, why)
    return dark


def mono_auto_set(scheme: int | None = None) -> str:
    return "mono-white" if decide_panel_is_dark(scheme) else "mono-black"


def watch_color_scheme(on_change: Callable[[int], None]) -> None:
    """Listen for portal SettingChanged(org.freedesktop.appearance, color-scheme)."""
    if not shutil.which("gdbus"):
        log.info("mono-auto: no gdbus, not watching for changes")
        return

    def loop() -> None:
        cmd = [
            "gdbus",
            "monitor",
            "--session",
            "--dest",
            "org.freedesktop.portal.Desktop",
            "--object-path",
            "/org/freedesktop/portal/desktop",
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
        except Exception as e:
            log.info("mono-auto: gdbus monitor failed: %r", e)
            return
        assert proc.stdout
        for line in proc.stdout:
            if "SettingChanged" in line and "color-scheme" in line:
                m = re.search(r"uint32 (\d+)", line)
                if m:
                    log.info("mono-auto: SettingChanged color-scheme=%s", m.group(1))
                    on_change(int(m.group(1)))

    threading.Thread(target=loop, daemon=True, name="tray-color-scheme").start()
    log.info("mono-auto: watching portal SettingChanged")


# ------------------------------------------------------------------ tray classes


def _xorg_subclass(base: Any, mode: str, sized: Callable[[int], Image.Image]) -> type:
    """Subclass of pystray._xorg.Icon (0.19.5) painting with real or faked alpha."""
    import Xlib.X
    import Xlib.Xatom
    import Xlib.Xutil

    def icon_for(w: int, h: int) -> Image.Image:
        s = min(w, h)
        im = sized(s)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.alpha_composite(im, ((w - s) // 2, (h - s) // 2))
        return canvas

    class XorgTray(base):
        _mode = mode

        def _create_window(self):
            screen = self._display.screen()
            kwargs: dict[str, Any] = {}
            depth = screen.root_depth
            self._argb = False
            if self._mode == "argb":
                vid, vdepth = self._tray_visual()
                if vid and vdepth == 32:
                    cmap = screen.root.create_colormap(vid, Xlib.X.AllocNone)
                    kwargs = dict(
                        visual=vid, colormap=cmap, border_pixel=0, background_pixel=0
                    )
                    depth = 32
                    self._argb = True
                log.info(
                    "xorg argb: tray visual=%s depth=%s -> argb=%s",
                    vid,
                    vdepth,
                    self._argb,
                )
            elif self._mode == "pseudo":
                kwargs = dict(background_pixmap=Xlib.X.ParentRelative)
            window = screen.root.create_window(
                -1,
                -1,
                1,
                1,
                0,
                depth,
                event_mask=Xlib.X.ExposureMask | Xlib.X.StructureNotifyMask,
                window_class=Xlib.X.InputOutput,
                **kwargs,
            )
            flags = Xlib.Xutil.PPosition | Xlib.Xutil.PSize | Xlib.Xutil.PMinSize
            window.set_wm_class(f"{self.name}SystemTrayIcon", self.name)
            window.set_wm_name(self.title)
            window.set_wm_normal_hints(flags=flags, min_width=24, min_height=24)
            window.change_property(
                self._xembed_info,
                self._xembed_info,
                32,
                [self._XEMBED_VERSION, self._XEMBED_MAPPED],
            )
            return window

        def _tray_visual(self):
            owner = self._display.get_selection_owner(self._net_system_tray_sx)
            if owner == Xlib.X.NONE:
                return None, None
            prop = owner.get_full_property(
                self._display.intern_atom("_NET_SYSTEM_TRAY_VISUAL"),
                Xlib.Xatom.VISUALID,
            )
            if not prop:
                return None, None
            vid = prop.value[0]
            for dep in self._display.screen().allowed_depths:
                if any(v.visual_id == vid for v in dep.visuals):
                    return vid, dep.depth
            return vid, None

        def _draw(self):
            try:
                dim = self._window.get_geometry()
                w, h = dim.width, dim.height
                icon = icon_for(w, h)
                if self._argb:
                    prem = icon.convert("RGBa")
                    r, g, b, a = prem.split()
                    data = Image.merge("RGBA", (b, g, r, a)).tobytes()
                    self._window.put_image(
                        self._gc, 0, 0, w, h, Xlib.X.ZPixmap, 32, 0, data
                    )
                    return
                if self._mode == "pseudo":
                    self._window.clear_area(0, 0, w, h)
                    self._display.sync()
                    raw = self._window.get_image(0, 0, w, h, Xlib.X.ZPixmap, 0xFFFFFFFF)
                    bg = Image.frombytes("RGB", (w, h), raw.data, "raw", "BGRX")
                    px = bg.getpixel((0, 0))
                    if getattr(self, "_logged_bg", None) != px:
                        self._logged_bg = px
                        log.info("xorg pseudo: read back parent bg pixel %s", px)
                    base_img = bg.convert("RGBA")
                elif self._mode.startswith("bg:"):
                    base_img = Image.new("RGBA", (w, h), (*self._bg_color(), 255))
                else:
                    base_img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
                base_img.alpha_composite(icon)
                out = base_img.convert("RGB")
                self._window.put_pil_image(self._gc, 0, 0, out)
            except Exception:
                log.error("xorg draw failed", exc_info=True)

        def _bg_color(self) -> tuple[int, int, int]:
            spec = self._mode[3:]
            if spec == "auto":
                return DARK_PANEL_GUESS if decide_panel_is_dark() else LIGHT_PANEL_GUESS
            spec = spec.lstrip("#")
            return (int(spec[0:2], 16), int(spec[2:4], 16), int(spec[4:6], 16))

    return XorgTray


def _appindicator_themed_subclass(base: Any, theme_path: str, icon_name: str) -> type:
    """pystray._appindicator.Icon (0.19.5) using an icon name + theme path, not a temp PNG."""
    from pystray._appindicator import AppIndicator  # type: ignore
    from pystray._util.gtk import mainloop  # type: ignore

    class ThemedTray(base):
        def _set_named_icon(self):
            self._appindicator.set_icon_theme_path(theme_path)
            self._appindicator.set_icon_full(icon_name, self.title)
            log.info("appindicator: icon name=%s theme_path=%s", icon_name, theme_path)

        @mainloop
        def _show(self):
            self._set_named_icon()
            self._appindicator.set_menu(
                self._menu_handle or self._create_default_menu()
            )
            self._appindicator.set_title(self.title)
            self._appindicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        @mainloop
        def _update_icon(self):
            self._set_named_icon()

    return ThemedTray


def start_glib_thread() -> None:
    from gi.repository import GLib  # type: ignore

    def run() -> None:
        log.info("glib: main loop thread running")
        GLib.MainLoop().run()

    threading.Thread(target=run, daemon=True, name="tray-glib").start()


def create_tray(
    base: Any,
    resource_path: Callable[[str], str],
    taskbar: Any,
    name: str,
    title: str,
    menu: Any,
) -> Any:
    """Build the tray icon object for the selected experiment."""
    if OPTIONS.backend == "sni":
        return create_sni_tray(resource_path, taskbar, name, title, menu)
    backend = log_backend_report()
    variant = OPTIONS.variant or "baseline"
    size = OPTIONS.size or 64
    cls = base
    watch_scheme = False

    if variant == "symbolic" and backend != "appindicator":
        log.info(
            "symbolic: backend is %s, not appindicator -> falling back to mono-auto",
            backend,
        )
        variant = "mono-auto"
    if variant == "themed" and backend != "appindicator":
        log.info(
            "themed: backend is %s, not appindicator -> falling back to color", backend
        )
        variant = "color"

    set_name: str | None = None
    if variant == "baseline":
        image = taskbar
    elif variant == "pr1814":
        image = pr1814_image(taskbar)
    elif variant in ASSET_VARIANTS:
        set_name = variant
        image = load_asset(resource_path, variant, size)
    elif variant == "mono-auto":
        set_name = mono_auto_set()
        image = load_asset(resource_path, set_name, size)
        watch_scheme = True
    elif variant == "symbolic":
        image = load_asset(resource_path, mono_auto_set(), size)
        cls = _appindicator_themed_subclass(
            base, str(icons_dir(resource_path) / "symbolic"), "kiln-symbolic"
        )
    elif variant == "themed":
        image = load_asset(resource_path, "color", size)
        cls = _appindicator_themed_subclass(
            base, str(icons_dir(resource_path) / "themed"), "kiln-tray-color"
        )
    else:
        raise ValueError(variant)

    state = {"set": set_name}
    if backend == "xorg" and OPTIONS.xorg != "stock":
        src_image = image

        def sized(s: int) -> Image.Image:
            if state["set"]:
                return load_asset(resource_path, state["set"], s)
            return src_image.convert("RGBA").resize((s, s), Image.Resampling.LANCZOS)

        cls = _xorg_subclass(cls, OPTIONS.xorg, sized)
    elif OPTIONS.xorg != "stock":
        log.info("--tray-xorg %s ignored: backend is %s", OPTIONS.xorg, backend)

    log.info(
        "tray: variant=%s set=%s image mode=%s size=%s class=%s",
        variant,
        set_name,
        image.mode,
        image.size,
        [
            f"{getattr(c, '__module__', '?')}.{getattr(c, '__name__', c)}"
            for c in getattr(cls, "__mro__", [cls])[:3]
        ],
    )
    tray = cls(name, image, title, menu)

    if watch_scheme:

        def on_change(scheme: int) -> None:
            new_set = mono_auto_set(scheme)
            if new_set != state["set"]:
                log.info("mono-auto: swapping %s -> %s", state["set"], new_set)
                state["set"] = new_set
                tray._icon_data = None
                tray.icon = load_asset(resource_path, new_set, size)

        watch_color_scheme(on_change)
    return tray


def load_all_sizes(
    resource_path: Callable[[str], str], set_name: str
) -> list[Image.Image]:
    d = icons_dir(resource_path) / set_name
    return [
        Image.open(p).convert("RGBA")
        for p in sorted(d.glob("kiln-*.png"), key=lambda p: int(p.stem.split("-")[1]))
    ]


def create_sni_tray(
    resource_path: Callable[[str], str],
    taskbar: Any,
    name: str,
    title: str,
    menu: Any,
) -> Any:
    """Pure D-Bus StatusNotifierItem (no GTK/gi), see tray_sni.py."""
    from app.desktop.tray_sni import SniTray

    variant = OPTIONS.variant or "baseline"
    icon_name = ""
    theme_path = ""
    set_name: str | None = None
    if variant == "baseline":
        pixmaps = [taskbar.convert("RGBA")]
    elif variant == "pr1814":
        pixmaps = [pr1814_image(taskbar).convert("RGBA")]
    elif variant in ASSET_VARIANTS:
        set_name = variant
    elif variant in ("mono-auto", "symbolic"):
        set_name = mono_auto_set()
    elif variant == "themed":
        set_name = "color"
    else:
        raise ValueError(variant)
    if set_name:
        pixmaps = load_all_sizes(resource_path, set_name)
    if variant == "symbolic":
        icon_name, theme_path = (
            "kiln-symbolic",
            str(icons_dir(resource_path) / "symbolic"),
        )
    elif variant == "themed":
        icon_name, theme_path = (
            "kiln-tray-color",
            str(icons_dir(resource_path) / "themed"),
        )

    items = list(menu)
    tray: Any = None

    def activate() -> None:
        items[0](tray)

    tray = SniTray(
        name,
        title,
        items,
        pixmaps,
        icon_name=icon_name,
        icon_theme_path=theme_path,
        activate=activate,
    )
    log.info(
        "tray: backend=sni variant=%s set=%s pixmaps=%s icon_name=%r theme_path=%r",
        variant,
        set_name,
        [p.size[0] for p in pixmaps],
        icon_name,
        theme_path,
    )
    if variant == "mono-auto":
        state = {"set": set_name}

        def on_change(scheme: int) -> None:
            new_set = mono_auto_set(scheme)
            if new_set != state["set"]:
                log.info("mono-auto: swapping %s -> %s", state["set"], new_set)
                state["set"] = new_set
                tray.set_pixmaps(load_all_sizes(resource_path, new_set))

        watch_color_scheme(on_change)
    return tray


def after_run_detached(tray: Any) -> None:
    backend = type(tray).__mro__[0].__module__
    mods = [c.__module__ for c in type(tray).__mro__]
    uses_glib = any(m in ("pystray._appindicator", "pystray._gtk") for m in mods)
    log.info(
        "run_detached done; glib backend=%s glib_thread=%s (%s)",
        uses_glib,
        OPTIONS.glib_thread,
        backend,
    )
    if uses_glib and OPTIONS.glib_thread:
        start_glib_thread()
