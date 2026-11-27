import pytest

from kiln_mcp_server.addresses import (
    app_origin,
    is_loopback_host,
    transport_security_for,
)

DEFAULT_NAMES = ["127.0.0.1", "localhost", "[::1]"]


def expected_hosts(names: list[str]) -> list[str]:
    return [entry for name in names for entry in (name, f"{name}:*")]


def expected_origins(names: list[str]) -> list[str]:
    return [entry for name in names for entry in (f"http://{name}", f"http://{name}:*")]


@pytest.mark.parametrize(
    "host", ["localhost", "LOCALHOST", "127.0.0.1", "127.0.0.2", "::1", "[::1]"]
)
def test_loopback_hosts(host):
    assert is_loopback_host(host)


@pytest.mark.parametrize(
    "host", ["0.0.0.0", "::", "", "192.168.1.5", "kiln.lan", "fd00::5", "[fd00::5]"]
)
def test_non_loopback_hosts(host):
    assert not is_loopback_host(host)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_loopback_bind_turns_protection_on(host):
    settings = transport_security_for(host)
    assert settings.enable_dns_rebinding_protection
    assert settings.allowed_hosts == expected_hosts(DEFAULT_NAMES)
    assert settings.allowed_origins == expected_origins(DEFAULT_NAMES)


def test_another_loopback_address_adds_itself():
    settings = transport_security_for("127.0.0.2")
    names = [*DEFAULT_NAMES, "127.0.0.2"]
    assert settings.allowed_hosts == expected_hosts(names)
    assert settings.allowed_origins == expected_origins(names)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "kiln.lan"])
def test_other_binds_turn_protection_off(host):
    settings = transport_security_for(host)
    assert not settings.enable_dns_rebinding_protection


@pytest.mark.parametrize(
    ("host", "port", "origin"),
    [
        ("127.0.0.1", 8757, "http://localhost:8757"),
        ("localhost", 8757, "http://localhost:8757"),
        ("::1", 8757, "http://localhost:8757"),
        ("[::1]", 8757, "http://localhost:8757"),
        ("0.0.0.0", 8757, "http://localhost:8757"),
        ("::", 8757, "http://localhost:8757"),
        ("", 8757, "http://localhost:8757"),
        ("127.0.0.1", 9000, "http://localhost:9000"),
        ("192.168.1.5", 8757, "http://192.168.1.5:8757"),
        ("kiln.lan", 8757, "http://kiln.lan:8757"),
        ("fd00::5", 8757, "http://[fd00::5]:8757"),
        ("[fd00::5]", 8757, "http://[fd00::5]:8757"),
    ],
)
def test_app_origin(host, port, origin):
    assert app_origin(host, port) == origin
