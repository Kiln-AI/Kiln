import io
import logging
import sys
from typing import Any, Type

logger = logging.getLogger(__name__)

try:
    import pystray

    IconBase: Type[Any] = pystray.Icon
    MenuItemBase: Type[Any] = pystray.MenuItem
except Exception:
    IconBase = object
    MenuItemBase = object


class KilnTray(IconBase):  # type: ignore
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # On Linux, bind left click to open the menu
        if sys.platform.startswith("linux"):
            self._setup_linux_click_menu()

    # --- Mac-specific behavior (already in your code) ---
    def _assert_image(self):
        if sys.platform != "darwin":
            super()._assert_image()  # type: ignore
            return

        import AppKit
        import Foundation

        thickness = self._status_bar.thickness()  # type: ignore
        logical_size = (int(thickness), int(thickness))
        if self._icon_image and self._icon_image.size() == logical_size:
            return

        source = self._icon
        b = io.BytesIO()
        source.save(b, "png")  # type: ignore
        data = Foundation.NSData(b.getvalue())  # type: ignore

        self._icon_image = AppKit.NSImage.alloc().initWithData_(data)  # type: ignore
        try:
            self._icon_image.setTemplate_(True)
            self._icon_image.setSize_(logical_size)
        except Exception:
            logger.error("Mac Tray Error", exc_info=True)
        self._status_item.button().setImage_(self._icon_image)  # type: ignore

    def _setup_linux_click_menu(self):
        """Bind left click to open tray menu"""
        try:
            listener = getattr(self, "_listener", None)
            if listener is not None:
                listener._on_left_click = lambda: self._show_menu()
        except Exception:
            logger.error("Linux Tray Click Error", exc_info=True)

    def _show_menu(self):
        """Force show the menu when left-clicked"""
        if self.menu:
            self.menu(self)  # show context menu


class KilnMenuItem(MenuItemBase):  # type: ignore - our dynamic type trips up pyright
    pass
