from unittest.mock import Mock

import pytest

from app.desktop.linux_tray.icons import Pixmap, TrayIcon
from app.desktop.linux_tray.sni_protocol import (
    MENU_PATH,
    DBusMenu,
    MenuItem,
    UnknownMenuItemError,
    UnknownMenuPropertyError,
    item_properties,
)


@pytest.fixture
def menu():
    return DBusMenu([MenuItem("Open", Mock()), MenuItem("Quit", Mock())])


def test_item_properties_expose_icon_name_theme_path_and_pixmaps():
    icon = TrayIcon("kiln-symbolic", "/icons", (Pixmap(1, 1, b"\xff\x00\x00\x00"),))

    properties = item_properties("kiln", "Kiln", icon)

    assert properties["IconName"] == ("s", "kiln-symbolic")
    assert properties["IconThemePath"] == ("s", "/icons")
    assert properties["IconPixmap"] == ("a(iiay)", [(1, 1, b"\xff\x00\x00\x00")])
    assert properties["Menu"] == ("o", MENU_PATH)
    assert properties["ItemIsMenu"] == ("b", False)
    for gnome_required in ("OverlayIconName", "AttentionIconPixmap", "XAyatanaLabel"):
        assert gnome_required in properties


def test_layout_lists_items_as_children_of_the_root(menu):
    root_id, root_properties, children = menu.layout(0, -1, [])

    assert root_id == 0
    assert root_properties == {"children-display": ("s", "submenu")}
    assert [child[1][1]["label"] for child in children] == [
        ("s", "Open"),
        ("s", "Quit"),
    ]
    assert [child[1][0] for child in children] == [1, 2]


def test_layout_honours_recursion_depth_and_property_filter(menu):
    assert menu.layout(0, 0, [])[2] == []
    assert menu.layout(2, -1, ["label"]) == (2, {"label": ("s", "Quit")}, [])


def test_group_properties_defaults_to_every_item_and_skips_unknown_ids(menu):
    assert [i for i, _ in menu.group_properties([], [])] == [1, 2]
    assert menu.group_properties([2, 99], ["enabled"]) == [
        (2, {"enabled": ("b", True)})
    ]


@pytest.mark.parametrize(
    "call, error",
    [
        (lambda m: m.item(0), UnknownMenuItemError),
        (lambda m: m.item(3), UnknownMenuItemError),
        (lambda m: m.layout(7, -1, []), UnknownMenuItemError),
        (lambda m: m.property(1, "icon-name"), UnknownMenuPropertyError),
    ],
)
def test_unknown_items_and_properties_raise(menu, call, error):
    with pytest.raises(error):
        call(menu)


def test_only_clicked_events_select_an_item(menu):
    assert menu.clicked_item(2, "clicked") is menu.item(2)
    assert menu.clicked_item(2, "hovered") is None


@pytest.mark.parametrize("event_id", ["opened", "closed", "clicked"])
def test_root_menu_events_select_nothing(menu, event_id):
    assert menu.clicked_item(0, event_id) is None
