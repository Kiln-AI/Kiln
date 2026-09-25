"""StatusNotifierItem and com.canonical.dbusmenu data, independent of the D-Bus transport.

Values are (signature, value) pairs, the form jeepney serialises as D-Bus variants.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.desktop.linux_tray.icons import TrayIcon

Variant = tuple[str, Any]
Properties = dict[str, Variant]

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
ITEM_INTERFACE = "org.kde.StatusNotifierItem"
MENU_INTERFACE = "com.canonical.dbusmenu"
WATCHER_BUS_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_INTERFACE = "org.kde.StatusNotifierWatcher"

PIXMAPS_SIGNATURE = "a(iiay)"
MENU_LAYOUT_SIGNATURE = "(ia{sv}av)"
DBUSMENU_VERSION = 3


def item_properties(item_id: str, title: str, icon: TrayIcon) -> Properties:
    pixmaps = [(p.width, p.height, p.argb32) for p in icon.pixmaps]
    # GNOME's AppIndicator extension reads the Overlay*, Attention* and XAyatana*
    # properties too, and shows a placeholder if any of them is missing.
    return {
        "Category": ("s", "ApplicationStatus"),
        "Id": ("s", item_id),
        "Title": ("s", title),
        "Status": ("s", "Active"),
        "WindowId": ("i", 0),
        "IconName": ("s", icon.name),
        "IconThemePath": ("s", icon.theme_path),
        "IconPixmap": (PIXMAPS_SIGNATURE, pixmaps),
        "ItemIsMenu": ("b", False),
        "Menu": ("o", MENU_PATH),
        "ToolTip": ("(sa(iiay)ss)", ("", [], title, "")),
        "OverlayIconName": ("s", ""),
        "OverlayIconPixmap": (PIXMAPS_SIGNATURE, []),
        "AttentionIconName": ("s", ""),
        "AttentionIconPixmap": (PIXMAPS_SIGNATURE, []),
        "AttentionMovieName": ("s", ""),
        "XAyatanaLabel": ("s", ""),
        "XAyatanaLabelGuide": ("s", ""),
    }


MENU_PROPERTIES: Properties = {
    "Version": ("u", DBUSMENU_VERSION),
    "TextDirection": ("s", "ltr"),
    "Status": ("s", "normal"),
    "IconThemePath": ("as", []),
}


@dataclass(frozen=True)
class MenuItem:
    label: str
    on_click: Callable[[], None]


class UnknownMenuItemError(LookupError):
    pass


class UnknownMenuPropertyError(LookupError):
    pass


class DBusMenu:
    """A flat menu: the root (id 0) with one child per item, ids starting at 1."""

    ROOT_ID = 0
    REVISION = 1

    def __init__(self, items: Sequence[MenuItem]):
        self._items = tuple(items)

    @property
    def item_ids(self) -> list[int]:
        return list(range(1, len(self._items) + 1))

    def item(self, item_id: int) -> MenuItem:
        if not 1 <= item_id <= len(self._items):
            raise UnknownMenuItemError(item_id)
        return self._items[item_id - 1]

    def layout(
        self, parent_id: int, recursion_depth: int, property_names: Sequence[str]
    ) -> tuple[int, Properties, list[Variant]]:
        if parent_id != self.ROOT_ID:
            return (parent_id, self.properties(parent_id, property_names), [])
        children: list[Variant] = []
        if recursion_depth != 0:
            children = [
                (
                    MENU_LAYOUT_SIGNATURE,
                    (item_id, self.properties(item_id, property_names), []),
                )
                for item_id in self.item_ids
            ]
        root = _only(
            {"children-display": ("s", "submenu")},
            property_names,
        )
        return (self.ROOT_ID, root, children)

    def properties(
        self, item_id: int, property_names: Sequence[str] = ()
    ) -> Properties:
        item = self.item(item_id)
        return _only(
            {
                "label": ("s", item.label),
                "enabled": ("b", True),
                "visible": ("b", True),
            },
            property_names,
        )

    def group_properties(
        self, item_ids: Sequence[int], property_names: Sequence[str]
    ) -> list[tuple[int, Properties]]:
        requested = item_ids or self.item_ids
        return [
            (item_id, self.properties(item_id, property_names))
            for item_id in requested
            if item_id in self.item_ids
        ]

    def property(self, item_id: int, name: str) -> Variant:
        properties = self.properties(item_id)
        if name not in properties:
            raise UnknownMenuPropertyError(name)
        return properties[name]

    def clicked_item(self, item_id: int, event_id: str) -> MenuItem | None:
        """The item to run for this event, or None if the event needs no action.

        Hosts send events such as "opened" and "closed" for the root menu too.
        """
        if item_id == self.ROOT_ID:
            return None
        item = self.item(item_id)
        return item if event_id == "clicked" else None


def _only(properties: Properties, names: Sequence[str]) -> Properties:
    """dbusmenu: an empty name list means every property."""
    if not names:
        return properties
    return {name: value for name, value in properties.items() if name in names}


INTROSPECTION_HEADER = (
    '<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"\n'
    ' "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">\n'
)

ROOT_INTROSPECTION_XML = (
    INTROSPECTION_HEADER
    + """<node>
  <node name="StatusNotifierItem"/>
  <node name="MenuBar"/>
</node>"""
)

ITEM_INTROSPECTION_XML = (
    INTROSPECTION_HEADER
    + """<node>
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
)

MENU_INTROSPECTION_XML = (
    INTROSPECTION_HEADER
    + """<node>
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
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
  </interface>
</node>"""
)

INTROSPECTION_XML_BY_PATH = {
    "/": ROOT_INTROSPECTION_XML,
    ITEM_PATH: ITEM_INTROSPECTION_XML,
    MENU_PATH: MENU_INTROSPECTION_XML,
}
