"""Linux tray icon as a StatusNotifierItem with a com.canonical.dbusmenu menu.

Speaks D-Bus directly through jeepney (pure Python), so the frozen app needs no
GTK or PyGObject. One daemon thread owns the receive side of the connection and
answers the panel's calls. Other threads may call `set_icon` and `stop`: jeepney's
threaded connection serialises sends, and `stop` interrupts the receiving thread.
"""

import sys

if sys.platform != "linux":
    raise ImportError("The StatusNotifierItem tray is only available on Linux")

import itertools
import logging
import os
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from jeepney import (
    DBusAddress,
    DBusNameFlags,
    HeaderFields,
    MatchRule,
    Message,
    MessageType,
    message_bus,
    new_error,
    new_method_call,
    new_method_return,
    new_signal,
)
from jeepney.io.threading import (
    DBusConnection,
    DBusRouter,
    Proxy,
    ReceiveStopped,
    open_dbus_connection,
)

from app.desktop.linux_tray.icons import TrayIcon, load_tray_icon
from app.desktop.linux_tray.sni_protocol import (
    INTROSPECTION_XML_BY_PATH,
    ITEM_INTERFACE,
    ITEM_PATH,
    MENU_INTERFACE,
    MENU_LAYOUT_SIGNATURE,
    MENU_PATH,
    MENU_PROPERTIES,
    WATCHER_BUS_NAME,
    WATCHER_INTERFACE,
    WATCHER_PATH,
    DBusMenu,
    MenuItem,
    Properties,
    UnknownMenuItemError,
    UnknownMenuPropertyError,
    item_properties,
)

logger = logging.getLogger(__name__)

BUS_CALL_TIMEOUT_SECONDS = 5.0
STOP_TIMEOUT_SECONDS = 5.0

INTROSPECTABLE_INTERFACE = "org.freedesktop.DBus.Introspectable"
PEER_INTERFACE = "org.freedesktop.DBus.Peer"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
BUS_DAEMON_NAME = "org.freedesktop.DBus"

ERROR_FAILED = "org.freedesktop.DBus.Error.Failed"
ERROR_INVALID_ARGS = "org.freedesktop.DBus.Error.InvalidArgs"
ERROR_PROPERTY_READ_ONLY = "org.freedesktop.DBus.Error.PropertyReadOnly"
ERROR_UNKNOWN_INTERFACE = "org.freedesktop.DBus.Error.UnknownInterface"
ERROR_UNKNOWN_METHOD = "org.freedesktop.DBus.Error.UnknownMethod"
ERROR_UNKNOWN_OBJECT = "org.freedesktop.DBus.Error.UnknownObject"
ERROR_UNKNOWN_PROPERTY = "org.freedesktop.DBus.Error.UnknownProperty"

REQUEST_NAME_PRIMARY_OWNER = 1

_WATCHER = DBusAddress(
    WATCHER_PATH, bus_name=WATCHER_BUS_NAME, interface=WATCHER_INTERFACE
)
_ITEM_SIGNAL_EMITTER = DBusAddress(ITEM_PATH, interface=ITEM_INTERFACE)
_item_instance_ids = itertools.count(1)


class StatusNotifierWatcherMissingError(RuntimeError):
    """No panel on the session bus is hosting StatusNotifierItems."""


class SniTray:
    """A tray icon registered with the panel's StatusNotifierWatcher.

    Owns `connection` from construction: `stop` closes it, which also removes
    the icon from the panel.
    """

    def __init__(
        self,
        connection: DBusConnection,
        *,
        item_id: str,
        title: str,
        icon: TrayIcon,
        menu_items: Sequence[MenuItem],
        on_activate: Callable[[], None],
    ):
        self._connection = connection
        self._item_id = item_id
        self._title = title
        self._icon = icon
        self._menu = DBusMenu(menu_items)
        self._on_activate = on_activate
        self.bus_name = (
            f"org.kde.StatusNotifierItem-{os.getpid()}-{next(_item_instance_ids)}"
        )
        self._lock = threading.Lock()
        self._stopped = False
        self._thread = threading.Thread(
            target=self._serve, name="kiln-sni-tray", daemon=True
        )

    def start(self) -> None:
        """Claim the item's bus name and register it with the watcher.

        Raises StatusNotifierWatcherMissingError if no panel hosts tray items.
        """
        with DBusRouter(self._connection) as router:
            bus = Proxy(message_bus, router, timeout=BUS_CALL_TIMEOUT_SECONDS)
            (watcher_present,) = bus.NameHasOwner(WATCHER_BUS_NAME)
            if not watcher_present:
                raise StatusNotifierWatcherMissingError()
            bus.AddMatch(_watcher_owner_changed_rule())
            (result,) = bus.RequestName(self.bus_name, DBusNameFlags.do_not_queue)
            if result != REQUEST_NAME_PRIMARY_OWNER:
                raise RuntimeError(f"Could not own D-Bus name {self.bus_name}")
        self._thread.start()
        self._register_with_watcher()

    def set_icon(self, icon: TrayIcon) -> None:
        """Replace the icon. Safe to call from any thread."""
        with self._lock:
            if self._stopped:
                return
            self._icon = icon
            self._connection.send(new_signal(_ITEM_SIGNAL_EMITTER, "NewIcon"))

    def stop(self) -> None:
        """Remove the icon and close the connection. Safe to call from any thread, more than once."""
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        self._connection.interrupt()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=STOP_TIMEOUT_SECONDS)
        self._connection.close()

    def _register_with_watcher(self) -> None:
        # Never wait for this reply: GNOME's AppIndicator extension calls back
        # into the item (Properties.GetAll) before it replies, and those calls
        # need the tray thread to be free to answer them.
        self._connection.send(
            new_method_call(
                _WATCHER, "RegisterStatusNotifierItem", "s", (self.bus_name,)
            )
        )

    def _serve(self) -> None:
        while True:
            try:
                message = self._connection.receive()
            except ReceiveStopped:
                return
            except Exception:
                logger.warning(
                    "Linux tray lost its D-Bus connection; the tray icon will stop responding",
                    exc_info=True,
                )
                return
            self._handle(message)

    def _handle(self, message: Message) -> None:
        message_type = message.header.message_type
        try:
            if message_type == MessageType.method_call:
                self._connection.send(self._reply(message))
            elif message_type == MessageType.signal:
                self._handle_signal(message)
            elif message_type == MessageType.error:
                logger.warning(
                    "Linux tray D-Bus call failed: %s %s",
                    message.header.fields.get(HeaderFields.error_name),
                    message.body,
                )
        except Exception:
            logger.error("Linux tray failed to handle a D-Bus message", exc_info=True)
            if message_type == MessageType.method_call:
                self._send_quietly(new_error(message, ERROR_FAILED))

    def _send_quietly(self, message: Message) -> None:
        try:
            self._connection.send(message)
        except Exception:
            logger.debug("Linux tray could not send a D-Bus error reply", exc_info=True)

    def _handle_signal(self, signal: Message) -> None:
        fields = signal.header.fields
        is_owner_change = (
            fields.get(HeaderFields.sender) == BUS_DAEMON_NAME
            and fields.get(HeaderFields.member) == "NameOwnerChanged"
        )
        if not is_owner_change:
            return
        name, _old_owner, new_owner = signal.body
        if name == WATCHER_BUS_NAME and new_owner:
            logger.info("StatusNotifierWatcher restarted; registering the tray again")
            self._register_with_watcher()

    def _reply(self, call: Message) -> Message:
        fields = call.header.fields
        path = fields.get(HeaderFields.path)
        interface = fields.get(HeaderFields.interface)
        member = fields.get(HeaderFields.member)

        if member == "Introspect" and interface in (None, INTROSPECTABLE_INTERFACE):
            xml = INTROSPECTION_XML_BY_PATH.get(path)
            if xml is None:
                return new_error(call, ERROR_UNKNOWN_OBJECT)
            return new_method_return(call, "s", (xml,))
        if member == "Ping" and interface in (None, PEER_INTERFACE):
            return new_method_return(call)
        if path == ITEM_PATH:
            if interface == PROPERTIES_INTERFACE:
                return _properties_reply(call, ITEM_INTERFACE, self._item_properties())
            if interface in (None, ITEM_INTERFACE):
                return self._item_reply(call, member)
        if path == MENU_PATH:
            if interface == PROPERTIES_INTERFACE:
                return _properties_reply(call, MENU_INTERFACE, MENU_PROPERTIES)
            if interface in (None, MENU_INTERFACE):
                return self._menu_reply(call, member)
        if path in INTROSPECTION_XML_BY_PATH:
            return new_error(call, ERROR_UNKNOWN_METHOD)
        return new_error(call, ERROR_UNKNOWN_OBJECT)

    def _item_properties(self) -> Properties:
        with self._lock:
            icon = self._icon
        return item_properties(self._item_id, self._title, icon)

    def _item_reply(self, call: Message, member: str) -> Message:
        if member == "Activate":
            _run_in_background(self._on_activate)
            return new_method_return(call)
        if member in ("SecondaryActivate", "ContextMenu", "Scroll"):
            return new_method_return(call)
        return new_error(call, ERROR_UNKNOWN_METHOD)

    def _menu_reply(self, call: Message, member: str) -> Message:
        menu = self._menu
        try:
            if member == "GetLayout":
                parent_id, recursion_depth, property_names = call.body
                layout = menu.layout(parent_id, recursion_depth, property_names)
                return new_method_return(
                    call, "u" + MENU_LAYOUT_SIGNATURE, (menu.REVISION, layout)
                )
            if member == "GetGroupProperties":
                item_ids, property_names = call.body
                return new_method_return(
                    call,
                    "a(ia{sv})",
                    (menu.group_properties(item_ids, property_names),),
                )
            if member == "GetProperty":
                item_id, name = call.body
                return new_method_return(call, "v", (menu.property(item_id, name),))
            if member == "Event":
                item_id, event_id, _data, _timestamp = call.body
                self._handle_menu_event(item_id, event_id)
                return new_method_return(call)
            if member == "EventGroup":
                (events,) = call.body
                id_errors = []
                for item_id, event_id, _data, _timestamp in events:
                    try:
                        self._handle_menu_event(item_id, event_id)
                    except UnknownMenuItemError:
                        id_errors.append(item_id)
                return new_method_return(call, "ai", (id_errors,))
            if member == "AboutToShow":
                (item_id,) = call.body
                if item_id != menu.ROOT_ID:
                    menu.item(item_id)
                return new_method_return(call, "b", (False,))
            if member == "AboutToShowGroup":
                (item_ids,) = call.body
                unknown = [
                    i for i in item_ids if i != menu.ROOT_ID and i not in menu.item_ids
                ]
                return new_method_return(call, "aiai", ([], unknown))
        except (UnknownMenuItemError, UnknownMenuPropertyError) as e:
            return new_error(call, ERROR_INVALID_ARGS, "s", (f"Unknown menu {e}",))
        return new_error(call, ERROR_UNKNOWN_METHOD)

    def _handle_menu_event(self, item_id: int, event_id: str) -> None:
        item = self._menu.clicked_item(item_id, event_id)
        if item is not None:
            _run_in_background(item.on_click)


def _properties_reply(call: Message, interface: str, properties: Properties) -> Message:
    member = call.header.fields.get(HeaderFields.member)
    requested_interface = call.body[0] if call.body else ""
    if requested_interface not in ("", interface):
        return new_error(call, ERROR_UNKNOWN_INTERFACE)
    if member == "GetAll":
        return new_method_return(call, "a{sv}", (properties,))
    if member == "Get":
        name = call.body[1]
        if name not in properties:
            return new_error(call, ERROR_UNKNOWN_PROPERTY)
        return new_method_return(call, "v", (properties[name],))
    if member == "Set":
        return new_error(call, ERROR_PROPERTY_READ_ONLY)
    return new_error(call, ERROR_UNKNOWN_METHOD)


def _watcher_owner_changed_rule() -> MatchRule:
    rule = MatchRule(
        type="signal",
        sender=BUS_DAEMON_NAME,
        interface=BUS_DAEMON_NAME,
        member="NameOwnerChanged",
    )
    rule.add_arg_condition(0, WATCHER_BUS_NAME)
    return rule


def _run_in_background(callback: Callable[[], None]) -> None:
    """Menu handlers may block (a browser launch), so keep them off the tray thread."""

    def run() -> None:
        try:
            callback()
        except Exception:
            logger.error("Linux tray menu action failed", exc_info=True)

    threading.Thread(target=run, name="kiln-sni-tray-action", daemon=True).start()


def start_sni_tray(
    *,
    title: str,
    icon_dir: Path,
    menu_items: Sequence[MenuItem],
    on_activate: Callable[[], None],
    bus: str = "SESSION",
) -> SniTray | None:
    """Show the tray through the panel's StatusNotifierWatcher.

    Returns None, without raising, when that isn't possible (no D-Bus session
    bus, no watcher, missing icon assets), so the caller can fall back.
    """
    try:
        icon = load_tray_icon(icon_dir)
        connection = open_dbus_connection(bus)
    except Exception:
        logger.warning(
            "Linux tray: D-Bus session bus or icon assets unavailable", exc_info=True
        )
        return None

    tray = SniTray(
        connection,
        item_id="kiln",
        title=title,
        icon=icon,
        menu_items=menu_items,
        on_activate=on_activate,
    )
    try:
        tray.start()
    except StatusNotifierWatcherMissingError:
        logger.info("Linux tray: no StatusNotifierWatcher on the session bus")
        tray.stop()
        return None
    except Exception:
        logger.warning(
            "Linux tray: StatusNotifierItem registration failed", exc_info=True
        )
        tray.stop()
        return None
    return tray
