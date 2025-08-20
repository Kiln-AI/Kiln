import io
import logging
import sys
from typing import Any, Type

logger = logging.getLogger(__name__)


# pystray runs unsafe code on import (crashes if not UI, such as in CI)
try:
    import pystray

    IconBase: Type[Any] = pystray.Icon
    MenuItemBase: Type[Any] = pystray.MenuItem
except Exception:
    # For CI, we should mock KilnTray in tests
    IconBase = object
    MenuItemBase = object


class KilnTray(IconBase):  # type: ignore - our dynamic type trips up pyright
    # Special handling for Mac to support dark/light mode and retina icons
    # lots of type ignores because we're accessing private attributes of pystray
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

        # Convert the PIL image to an NSImage
        b = io.BytesIO()
        source.save(b, "png")  # type: ignore
        data = Foundation.NSData(b.getvalue())  # type: ignore

        self._icon_image = AppKit.NSImage.alloc().initWithData_(data)  # type: ignore
        try:
            # template image will respect dark/light mode
            self._icon_image.setTemplate_(True)
            # set the logical size of the image, which will be scaled for retina
            self._icon_image.setSize_(logical_size)
        except Exception:
            # Continue, this shouldn't be fatal
            logger.error("Mac Tray Error", exc_info=True)
        self._status_item.button().setImage_(self._icon_image)  # type: ignore


class KilnMenuItem(MenuItemBase):  # type: ignore - our dynamic type trips up pyright
    pass
