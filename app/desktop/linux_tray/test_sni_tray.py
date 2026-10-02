import queue
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

if sys.platform != "linux" or shutil.which("dbus-daemon") is None:
    pytest.skip(
        "needs Linux and dbus-daemon for a private session bus",
        allow_module_level=True,
    )

pytest.importorskip("jeepney")

from jeepney import (
    DBusAddress,
    DBusErrorResponse,
    DBusNameFlags,
    MatchRule,
    Message,
    message_bus,
    new_error,
    new_method_call,
    new_method_return,
)
from jeepney.io.threading import (
    DBusRouter,
    Proxy,
    open_dbus_connection,
)

from app.desktop.linux_tray.icons import Pixmap, TrayIcon
from app.desktop.linux_tray.sni_protocol import (
    ITEM_INTERFACE,
    ITEM_PATH,
    MENU_INTERFACE,
    MENU_PATH,
    WATCHER_BUS_NAME,
    WATCHER_INTERFACE,
    MenuItem,
)
from app.desktop.linux_tray.sni_tray import SniTray, start_sni_tray

ICON_DIR = Path(__file__).parent / "icons"
TIMEOUT = 5.0
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"


@contextmanager
def private_bus(tmp_path: Path) -> Iterator[tuple[subprocess.Popen, str]]:
    daemon = subprocess.Popen(
        [
            "dbus-daemon",
            "--session",
            "--nofork",
            "--nopidfile",
            f"--address=unix:path={tmp_path / 'bus'}",
            "--print-address=1",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert daemon.stdout is not None
    address = daemon.stdout.readline().strip()
    try:
        yield daemon, address
    finally:
        daemon.terminate()
        daemon.wait(timeout=TIMEOUT)


@pytest.fixture
def bus_address(tmp_path) -> Iterator[str]:
    with private_bus(tmp_path) as (_daemon, address):
        yield address


class BusClient:
    """Plays the panel: calls into the tray item and watches its signals."""

    def __init__(self, address: str):
        self.closed = False
        self.connection = open_dbus_connection(address)
        self.router = DBusRouter(self.connection)
        self.bus = Proxy(message_bus, self.router, timeout=TIMEOUT)

    def call(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str | None = None,
        body: tuple = (),
    ) -> tuple:
        address = DBusAddress(path, bus_name=destination, interface=interface)
        reply = self.router.send_and_get_reply(
            new_method_call(address, member, signature, body), timeout=TIMEOUT
        )
        if reply.header.message_type.name == "error":
            raise DBusErrorResponse(reply)
        return reply.body

    def get_all(self, destination: str, path: str, interface: str) -> dict:
        (properties,) = self.call(
            destination, path, PROPERTIES_INTERFACE, "GetAll", "s", (interface,)
        )
        return {name: value for name, (_signature, value) in properties.items()}

    def watch_signals(self, rule: MatchRule) -> "queue.Queue[Message]":
        signals: queue.Queue[Message] = queue.Queue()
        self.router.filter(rule, queue=signals)
        self.bus.AddMatch(rule)
        return signals

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.router.close()
            self.connection.close()


class FakeWatcher(BusClient):
    """A StatusNotifierWatcher that, like GNOME's AppIndicator extension, reads
    the item's properties before it replies to RegisterStatusNotifierItem."""

    def __init__(self, address: str, reject_with: str | None = None):
        super().__init__(address)
        self._reject_with = reject_with
        self.registrations: queue.Queue[tuple[str, dict]] = queue.Queue()
        self._calls: queue.Queue[Message | None] = queue.Queue()
        self.router.filter(
            MatchRule(type="method_call", interface=WATCHER_INTERFACE),
            queue=self._calls,
        )
        self.bus.RequestName(WATCHER_BUS_NAME, DBusNameFlags.do_not_queue)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while (call := self._calls.get()) is not None:
            (item_bus_name,) = call.body
            properties = self.get_all(item_bus_name, ITEM_PATH, ITEM_INTERFACE)
            if self._reject_with:
                self.router.send(new_error(call, self._reject_with))
            else:
                self.router.send(new_method_return(call))
            self.registrations.put((item_bus_name, properties))

    def next_registration(self) -> tuple[str, dict]:
        return self.registrations.get(timeout=TIMEOUT)

    def close(self) -> None:
        if self.closed:
            return
        self._calls.put(None)
        self._thread.join(timeout=TIMEOUT)
        super().close()


@pytest.fixture
def watcher(bus_address) -> Iterator[FakeWatcher]:
    watcher = FakeWatcher(bus_address)
    yield watcher
    watcher.close()


@pytest.fixture
def client(bus_address) -> Iterator[BusClient]:
    client = BusClient(bus_address)
    yield client
    client.close()


class Callbacks:
    def __init__(self):
        self.fired: queue.Queue[str] = queue.Queue()

    def recorder(self, name: str):
        return lambda: self.fired.put(name)

    def next(self) -> str:
        return self.fired.get(timeout=TIMEOUT)


@pytest.fixture
def callbacks() -> Callbacks:
    return Callbacks()


@pytest.fixture
def tray(bus_address, watcher, callbacks) -> Iterator[SniTray]:
    tray = start_sni_tray(
        title="Kiln",
        icon_dir=ICON_DIR,
        menu_items=[
            MenuItem("Open Kiln Studio", callbacks.recorder("open")),
            MenuItem("Quit", callbacks.recorder("quit")),
        ],
        on_activate=callbacks.recorder("activate"),
        bus=bus_address,
    )
    assert tray is not None
    watcher.next_registration()
    yield tray
    tray.stop()


def item_call(client, tray, member, signature=None, body=()):
    return client.call(
        tray.bus_name, ITEM_PATH, ITEM_INTERFACE, member, signature, body
    )


def menu_call(client, tray, member, signature=None, body=()):
    return client.call(
        tray.bus_name, MENU_PATH, MENU_INTERFACE, member, signature, body
    )


def test_registers_with_a_watcher_that_reads_properties_before_replying(
    bus_address, watcher
):
    tray = start_sni_tray(
        title="Kiln",
        icon_dir=ICON_DIR,
        menu_items=[],
        on_activate=Mock(),
        bus=bus_address,
    )
    assert tray is not None
    try:
        bus_name, properties = watcher.next_registration()
    finally:
        tray.stop()

    assert bus_name == tray.bus_name
    assert properties["Id"] == "kiln"
    assert properties["Title"] == "Kiln"
    assert properties["Status"] == "Active"
    assert properties["IconName"] == "kiln-symbolic"
    assert properties["IconThemePath"] == str(ICON_DIR)
    assert properties["Menu"] == MENU_PATH
    assert [(w, h) for w, h, _ in properties["IconPixmap"]] == [
        (16, 16),
        (22, 22),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
    ]


def test_property_get_and_errors(client, tray):
    def get(interface, name):
        return client.call(
            tray.bus_name,
            ITEM_PATH,
            PROPERTIES_INTERFACE,
            "Get",
            "ss",
            (interface, name),
        )

    assert get(ITEM_INTERFACE, "Title") == (("s", "Kiln"),)
    assert get("", "ItemIsMenu") == (("b", False),)
    with pytest.raises(DBusErrorResponse, match="UnknownProperty"):
        get(ITEM_INTERFACE, "Nope")
    with pytest.raises(DBusErrorResponse, match="UnknownInterface"):
        get("org.example.Other", "Title")
    with pytest.raises(DBusErrorResponse, match="PropertyReadOnly"):
        client.call(
            tray.bus_name,
            ITEM_PATH,
            PROPERTIES_INTERFACE,
            "Set",
            "ssv",
            (ITEM_INTERFACE, "Title", ("s", "x")),
        )


def test_menu_properties(client, tray):
    assert client.get_all(tray.bus_name, MENU_PATH, MENU_INTERFACE) == {
        "Version": 3,
        "TextDirection": "ltr",
        "Status": "normal",
        "IconThemePath": [],
    }


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/", '<node name="StatusNotifierItem"/>'),
        (ITEM_PATH, '<interface name="org.kde.StatusNotifierItem">'),
        (MENU_PATH, '<interface name="com.canonical.dbusmenu">'),
    ],
)
def test_introspection(client, tray, path, expected):
    (xml,) = client.call(
        tray.bus_name, path, "org.freedesktop.DBus.Introspectable", "Introspect"
    )
    assert expected in xml


@pytest.mark.parametrize(
    "path, interface, member, error",
    [
        ("/Nope", ITEM_INTERFACE, "Activate", "UnknownObject"),
        ("/Nope", "org.freedesktop.DBus.Introspectable", "Introspect", "UnknownObject"),
        (ITEM_PATH, ITEM_INTERFACE, "Frobnicate", "UnknownMethod"),
        (MENU_PATH, MENU_INTERFACE, "Frobnicate", "UnknownMethod"),
        ("/", "org.example.Other", "Anything", "UnknownMethod"),
        (ITEM_PATH, PROPERTIES_INTERFACE, "Frobnicate", "UnknownMethod"),
    ],
)
def test_unknown_objects_and_methods(client, tray, path, interface, member, error):
    with pytest.raises(DBusErrorResponse, match=error):
        client.call(tray.bus_name, path, interface, member)


def test_ping(client, tray):
    assert (
        client.call(tray.bus_name, ITEM_PATH, "org.freedesktop.DBus.Peer", "Ping") == ()
    )


def test_menu_layout(client, tray):
    revision, (root_id, root_properties, children) = menu_call(
        client, tray, "GetLayout", "iias", (0, -1, [])
    )

    assert revision == 1
    assert root_id == 0
    assert root_properties == {"children-display": ("s", "submenu")}
    labels = [child[1]["label"] for _signature, child in children]
    assert labels == [("s", "Open Kiln Studio"), ("s", "Quit")]


def test_menu_item_queries(client, tray):
    (properties,) = menu_call(
        client, tray, "GetGroupProperties", "aias", ([2], ["label"])
    )
    assert properties == [(2, {"label": ("s", "Quit")})]
    assert menu_call(client, tray, "GetProperty", "is", (1, "enabled")) == (
        ("b", True),
    )
    assert menu_call(client, tray, "AboutToShow", "i", (0,)) == (False,)
    assert menu_call(client, tray, "AboutToShowGroup", "ai", ([0, 1, 9],)) == (
        [],
        [9],
    )
    with pytest.raises(DBusErrorResponse, match="InvalidArgs"):
        menu_call(client, tray, "GetProperty", "is", (1, "icon-name"))
    with pytest.raises(DBusErrorResponse, match="InvalidArgs"):
        menu_call(client, tray, "AboutToShow", "i", (9,))


def test_activate_runs_the_activate_callback(client, tray, callbacks):
    item_call(client, tray, "Activate", "ii", (0, 0))

    assert callbacks.next() == "activate"


@pytest.mark.parametrize("member", ["SecondaryActivate", "ContextMenu"])
def test_other_clicks_do_nothing(client, tray, callbacks, member):
    item_call(client, tray, member, "ii", (0, 0))
    item_call(client, tray, "Activate", "ii", (0, 0))

    assert callbacks.next() == "activate"


def test_menu_click_runs_that_items_callback(client, tray, callbacks):
    menu_call(client, tray, "Event", "isvu", (2, "hovered", ("s", ""), 0))
    menu_call(client, tray, "Event", "isvu", (2, "clicked", ("s", ""), 0))

    assert callbacks.next() == "quit"
    assert callbacks.fired.empty()


def test_menu_event_group_reports_unknown_items(client, tray, callbacks):
    (id_errors,) = menu_call(
        client,
        tray,
        "EventGroup",
        "a(isvu)",
        (
            [
                (0, "opened", ("s", ""), 0),
                (9, "clicked", ("s", ""), 0),
                (1, "clicked", ("s", ""), 0),
            ],
        ),
    )

    assert id_errors == [9]
    assert callbacks.next() == "open"


@pytest.mark.parametrize("event_id", ["opened", "closed"])
def test_root_menu_open_and_close_events_succeed(client, tray, callbacks, event_id):
    assert menu_call(client, tray, "Event", "isvu", (0, event_id, ("s", ""), 0)) == ()
    assert callbacks.fired.empty()


def test_menu_event_for_unknown_item_is_an_error(client, tray):
    with pytest.raises(DBusErrorResponse, match="InvalidArgs"):
        menu_call(client, tray, "Event", "isvu", (9, "clicked", ("s", ""), 0))


def test_failing_callback_does_not_break_the_tray(bus_address, watcher, client):
    failing = Mock(side_effect=RuntimeError("boom"))
    tray = start_sni_tray(
        title="Kiln",
        icon_dir=ICON_DIR,
        menu_items=[],
        on_activate=failing,
        bus=bus_address,
    )
    assert tray is not None
    try:
        watcher.next_registration()
        item_call(client, tray, "Activate", "ii", (0, 0))
        item_call(client, tray, "Activate", "ii", (0, 0))
        assert client.get_all(tray.bus_name, ITEM_PATH, ITEM_INTERFACE)["Id"] == "kiln"
    finally:
        tray.stop()
    assert failing.call_count == 2


def test_set_icon_emits_new_icon_and_serves_the_new_icon(client, tray):
    new_icons = client.watch_signals(
        MatchRule(type="signal", interface=ITEM_INTERFACE, member="NewIcon")
    )
    replacement = TrayIcon("other-icon", "/elsewhere", (Pixmap(1, 1, b"\0\0\0\0"),))

    threading.Thread(target=tray.set_icon, args=(replacement,)).start()

    new_icons.get(timeout=TIMEOUT)
    properties = client.get_all(tray.bus_name, ITEM_PATH, ITEM_INTERFACE)
    assert properties["IconName"] == "other-icon"
    assert properties["IconThemePath"] == "/elsewhere"
    assert properties["IconPixmap"] == [(1, 1, b"\0\0\0\0")]


def test_stop_releases_the_bus_name_and_is_idempotent(client, tray):
    assert client.bus.NameHasOwner(tray.bus_name) == (True,)

    tray.stop()
    tray.stop()
    tray.set_icon(TrayIcon("ignored", "", ()))

    assert client.bus.NameHasOwner(tray.bus_name) == (False,)


def test_registers_again_when_the_watcher_restarts(bus_address, watcher, tray):
    watcher.close()
    replacement = FakeWatcher(bus_address)
    try:
        bus_name, properties = replacement.next_registration()
    finally:
        replacement.close()

    assert bus_name == tray.bus_name
    assert properties["IconName"] == "kiln-symbolic"


def test_returns_none_without_a_watcher(bus_address, client):
    tray = start_sni_tray(
        title="Kiln",
        icon_dir=ICON_DIR,
        menu_items=[],
        on_activate=Mock(),
        bus=bus_address,
    )

    assert tray is None
    (names,) = client.bus.ListNames()
    assert not [n for n in names if n.startswith("org.kde.StatusNotifierItem-")]


def test_returns_none_when_the_bus_is_unreachable(tmp_path):
    assert (
        start_sni_tray(
            title="Kiln",
            icon_dir=ICON_DIR,
            menu_items=[],
            on_activate=Mock(),
            bus=f"unix:path={tmp_path / 'no-bus'}",
        )
        is None
    )


def test_returns_none_when_icons_are_missing(bus_address, watcher, tmp_path):
    assert (
        start_sni_tray(
            title="Kiln",
            icon_dir=tmp_path,
            menu_items=[],
            on_activate=Mock(),
            bus=bus_address,
        )
        is None
    )
    assert watcher.registrations.empty()


def start_minimal_tray(bus_address, **overrides):
    arguments = {
        "title": "Kiln",
        "icon_dir": ICON_DIR,
        "menu_items": [],
        "on_activate": Mock(),
        "bus": bus_address,
    } | overrides
    return start_sni_tray(**arguments)


def test_logs_when_the_watcher_rejects_the_item(bus_address, caplog):
    rejecting = FakeWatcher(bus_address, reject_with="org.example.Error.Rejected")
    tray = start_minimal_tray(bus_address)
    assert tray is not None
    try:
        rejecting.next_registration()
        # A round trip through the tray thread guarantees it has seen the error reply.
        client = BusClient(bus_address)
        client.get_all(tray.bus_name, ITEM_PATH, ITEM_INTERFACE)
        client.close()
    finally:
        tray.stop()
        rejecting.close()

    assert "org.example.Error.Rejected" in caplog.text


def test_a_failing_handler_replies_with_an_error_and_keeps_serving(client, tray):
    with patch(
        "app.desktop.linux_tray.sni_tray.item_properties",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(DBusErrorResponse, match="Failed"):
            client.get_all(tray.bus_name, ITEM_PATH, ITEM_INTERFACE)

    assert client.get_all(tray.bus_name, ITEM_PATH, ITEM_INTERFACE)["Id"] == "kiln"


# The fake watcher's jeepney receiver thread dies with the bus too, and pytest reports that.
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_tray_thread_exits_when_the_bus_goes_away(tmp_path, caplog):
    with private_bus(tmp_path) as (daemon, address):
        watcher = FakeWatcher(address)
        tray = start_minimal_tray(address)
        assert tray is not None
        watcher.next_registration()
        daemon.terminate()
        daemon.wait(timeout=TIMEOUT)

        tray._thread.join(timeout=TIMEOUT)

    assert not tray._thread.is_alive()
    assert "lost its D-Bus connection" in caplog.text
    tray.stop()
    watcher.close()


def test_returns_none_and_cleans_up_when_registration_fails(bus_address, watcher):
    with (
        patch.object(SniTray, "start", side_effect=RuntimeError("boom")),
        patch.object(SniTray, "stop") as stop,
    ):
        assert start_minimal_tray(bus_address) is None

    stop.assert_called_once()
