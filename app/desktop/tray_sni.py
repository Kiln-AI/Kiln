"""Minimal pure-Python StatusNotifierItem + com.canonical.dbusmenu tray (experiment).

No GTK / PyGObject: speaks D-Bus directly with jeepney (pure Python). Selected with
`--tray-backend sni`. Supports:

- IconPixmap: several ARGB32 sizes, so the host picks the best one (real alpha)
- IconName + IconThemePath: for the `symbolic` variant (host recolors)
- a real menu via com.canonical.dbusmenu, Activate (left click) opens the studio
- re-registering when the StatusNotifierWatcher (panel) restarts
"""

import logging
import os
import queue
import threading
from typing import Any, Callable

from jeepney import (
    DBusAddress,
    HeaderFields,
    MessageType,
    new_error,
    new_method_call,
    new_method_return,
    new_signal,
)
from jeepney.io.blocking import open_dbus_connection
from PIL import Image

log = logging.getLogger("kiln.tray")

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
SNI_IFACE = "org.kde.StatusNotifierItem"
MENU_IFACE = "com.canonical.dbusmenu"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
WATCHER = DBusAddress(
    "/StatusNotifierWatcher",
    bus_name="org.kde.StatusNotifierWatcher",
    interface="org.kde.StatusNotifierWatcher",
)
BUS = DBusAddress(
    "/org/freedesktop/DBus",
    bus_name="org.freedesktop.DBus",
    interface="org.freedesktop.DBus",
)

INTROSPECT_XML = """<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
    <property name="AttentionMovieName" type="s" access="read"/>
    <property name="XAyatanaLabel" type="s" access="read"/>
    <property name="XAyatanaLabelGuide" type="s" access="read"/>
    <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
    <signal name="NewIcon"/>
    <signal name="NewTitle"/>
    <signal name="NewStatus"><arg name="status" type="s"/></signal>
  </interface>
</node>"""

MENU_INTROSPECT_XML = """<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" name="events" direction="in"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <method name="AboutToShowGroup">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="ai" name="updatesNeeded" direction="out"/>
      <arg type="ai" name="idErrors" direction="out"/>
    </method>
    <signal name="LayoutUpdated"><arg type="u" name="revision"/><arg type="i" name="parent"/></signal>
  </interface>
</node>"""


def _argb32(im: Image.Image) -> tuple[int, int, bytes]:
    """SNI pixmaps are ARGB32 in network byte order, straight (non-premultiplied) alpha."""
    rgba = im.convert("RGBA")
    r, g, b, a = rgba.split()
    data = Image.merge("RGBA", (a, r, g, b)).tobytes()
    return (rgba.width, rgba.height, data)


class SniTray:
    """Duck-types the bits of pystray.Icon that DesktopApp uses."""

    def __init__(
        self,
        name: str,
        title: str,
        menu: Any,
        pixmaps: list[Image.Image],
        icon_name: str = "",
        icon_theme_path: str = "",
        activate: Callable[[], None] | None = None,
    ):
        self.name = name
        self.title = title
        self.menu_items = list(menu)
        self._pixmaps = [_argb32(p) for p in pixmaps]
        self._icon_name = icon_name
        self._theme_path = icon_theme_path
        self._activate = activate
        self._icon_data = None
        self._bus_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._conn: Any = None
        self._revision = 1

    # -- pystray-compatible surface

    @property
    def icon(self) -> Any:
        return None

    @icon.setter
    def icon(self, image: Image.Image) -> None:
        sizes = [16, 22, 24, 32, 48, 64]
        self.set_pixmaps(
            [image.resize((s, s), Image.Resampling.LANCZOS) for s in sizes]
        )

    def set_pixmaps(self, images: list[Image.Image]) -> None:
        self._pixmaps = [_argb32(p) for p in images]
        self._queue.put(("signal", "NewIcon"))

    def run_detached(self) -> None:
        self._conn = open_dbus_connection(bus="SESSION")
        reply = self._conn.send_and_get_reply(
            new_method_call(BUS, "RequestName", "su", (self._bus_name, 0))
        )
        log.info("sni: RequestName %s -> %s", self._bus_name, reply.body)
        self._conn.send_and_get_reply(
            new_method_call(
                BUS,
                "AddMatch",
                "s",
                (
                    "type='signal',interface='org.freedesktop.DBus',member='NameOwnerChanged',"
                    "arg0='org.kde.StatusNotifierWatcher'",
                ),
            )
        )
        self._register()
        threading.Thread(target=self._loop, daemon=True, name="tray-sni").start()

    def stop(self) -> None:
        self._stop.set()

    # -- D-Bus plumbing

    def _register(self) -> None:
        # Fire-and-forget: hosts (e.g. GNOME's AppIndicator extension) call back
        # into us before replying, and send_and_get_reply would drop those calls.
        self._conn.send(
            new_method_call(
                WATCHER, "RegisterStatusNotifierItem", "s", (self._bus_name,)
            )
        )
        log.info("sni: RegisterStatusNotifierItem sent")

    def _loop(self) -> None:
        while not self._stop.is_set():
            while not self._queue.empty():
                kind, arg = self._queue.get()
                if kind == "signal":
                    addr = DBusAddress(ITEM_PATH, interface=SNI_IFACE)
                    self._conn.send(new_signal(addr, arg))
                    log.info("sni: emitted %s", arg)
            try:
                msg = self._conn.receive(timeout=0.2)
            except TimeoutError:
                continue
            except Exception:
                log.error("sni: receive failed", exc_info=True)
                return
            try:
                self._dispatch(msg)
            except Exception:
                log.error("sni: dispatch failed", exc_info=True)
                if msg.header.message_type == MessageType.method_call:
                    self._conn.send(new_error(msg, "org.freedesktop.DBus.Error.Failed"))

    def _dispatch(self, msg: Any) -> None:
        f = msg.header.fields
        mtype = msg.header.message_type
        member = f.get(HeaderFields.member)
        if mtype == MessageType.signal:
            if member == "NameOwnerChanged" and msg.body[2]:
                log.info("sni: watcher (re)appeared, registering")
                self._register()
            return
        if mtype == MessageType.error:
            log.info("sni: error reply %s %s", f.get(HeaderFields.error_name), msg.body)
            return
        if mtype != MessageType.method_call:
            return
        path = f.get(HeaderFields.path)
        iface = f.get(HeaderFields.interface)
        send = self._conn.send
        log.debug("sni: call %s %s.%s %s", path, iface, member, str(msg.body)[:120])

        if iface == "org.freedesktop.DBus.Introspectable" or member == "Introspect":
            xml = MENU_INTROSPECT_XML if path == MENU_PATH else INTROSPECT_XML
            send(new_method_return(msg, "s", (xml,)))
            return
        if iface == "org.freedesktop.DBus.Peer" and member == "Ping":
            send(new_method_return(msg))
            return
        if iface == PROPS_IFACE:
            props = self._menu_props() if path == MENU_PATH else self._item_props()
            if member == "GetAll":
                send(new_method_return(msg, "a{sv}", (props,)))
            elif member == "Get":
                prop = msg.body[1]
                if prop in props:
                    send(new_method_return(msg, "v", (props[prop],)))
                else:
                    send(new_error(msg, "org.freedesktop.DBus.Error.UnknownProperty"))
            else:
                send(new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod"))
            return
        if path == ITEM_PATH:
            log.info("sni: %s%s", member, msg.body)
            if member in ("Activate", "SecondaryActivate") and self._activate:
                self._activate()
            send(new_method_return(msg))
            return
        if path == MENU_PATH:
            self._menu_call(msg, member)
            return
        send(new_error(msg, "org.freedesktop.DBus.Error.UnknownObject"))

    def _item_props(self) -> dict[str, tuple[str, Any]]:
        return {
            "Category": ("s", "ApplicationStatus"),
            "Id": ("s", self.name),
            "Title": ("s", self.title),
            "Status": ("s", "Active"),
            "WindowId": ("i", 0),
            "IconName": ("s", self._icon_name),
            "IconThemePath": ("s", self._theme_path),
            "IconPixmap": ("a(iiay)", self._pixmaps),
            "ItemIsMenu": ("b", False),
            "Menu": ("o", MENU_PATH),
            "ToolTip": ("(sa(iiay)ss)", ("", [], self.title, "")),
            "OverlayIconName": ("s", ""),
            "OverlayIconPixmap": ("a(iiay)", []),
            "AttentionIconName": ("s", ""),
            "AttentionIconPixmap": ("a(iiay)", []),
            "AttentionMovieName": ("s", ""),
            "XAyatanaLabel": ("s", ""),
            "XAyatanaLabelGuide": ("s", ""),
        }

    def _menu_props(self) -> dict[str, tuple[str, Any]]:
        return {
            "Version": ("u", 3),
            "TextDirection": ("s", "ltr"),
            "Status": ("s", "normal"),
            "IconThemePath": ("as", []),
        }

    def _menu_item(self, idx: int) -> tuple[int, dict[str, tuple[str, Any]], list]:
        item = self.menu_items[idx - 1]
        return (
            idx,
            {
                "label": ("s", item.text),
                "enabled": ("b", True),
                "visible": ("b", True),
            },
            [],
        )

    def _menu_call(self, msg: Any, member: str) -> None:
        send = self._conn.send
        if member == "GetLayout":
            parent = msg.body[0]
            if parent == 0:
                children = [
                    ("(ia{sv}av)", self._menu_item(i + 1))
                    for i in range(len(self.menu_items))
                ]
                layout = (0, {"children-display": ("s", "submenu")}, children)
            else:
                layout = self._menu_item(parent)
            send(new_method_return(msg, "u(ia{sv}av)", (self._revision, layout)))
        elif member == "GetGroupProperties":
            ids = msg.body[0] or list(range(1, len(self.menu_items) + 1))
            out = [
                (i, self._menu_item(i)[1])
                for i in ids
                if 1 <= i <= len(self.menu_items)
            ]
            send(new_method_return(msg, "a(ia{sv})", (out,)))
        elif member == "GetProperty":
            i, name = msg.body
            send(new_method_return(msg, "v", (self._menu_item(i)[1][name],)))
        elif member == "Event":
            i, event_id = msg.body[0], msg.body[1]
            send(new_method_return(msg))
            self._menu_event(i, event_id)
        elif member == "EventGroup":
            send(new_method_return(msg, "ai", ([],)))
            for i, event_id, _data, _ts in msg.body[0]:
                self._menu_event(i, event_id)
        elif member == "AboutToShow":
            send(new_method_return(msg, "b", (False,)))
        elif member == "AboutToShowGroup":
            send(new_method_return(msg, "aiai", ([], [])))
        else:
            send(new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod"))

    def _menu_event(self, i: int, event_id: str) -> None:
        log.info("sni: menu event id=%s %s", i, event_id)
        if event_id == "clicked" and 1 <= i <= len(self.menu_items):
            item = self.menu_items[i - 1]
            threading.Thread(target=item, args=(self,), daemon=True).start()
