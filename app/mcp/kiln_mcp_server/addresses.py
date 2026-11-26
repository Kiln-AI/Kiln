"""Address rules for the MCP server: which Host and Origin headers it accepts,
and the address of the Kiln app as users see it."""

import ipaddress

from mcp.server.transport_security import TransportSecuritySettings

_LOOPBACK_NAMES = ("127.0.0.1", "localhost", "[::1]")


def _strip_brackets(host: str) -> str:
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(_strip_brackets(host))
    except ValueError:
        return None


def _url_host(ip_or_name: str) -> str:
    """The host as written in a URL or Host header: IPv6 literals in brackets."""
    ip = _parse_ip(ip_or_name)
    if isinstance(ip, ipaddress.IPv6Address):
        return f"[{ip.compressed}]"
    return _strip_brackets(ip_or_name)


def is_loopback_host(host: str) -> bool:
    if _strip_brackets(host).lower() == "localhost":
        return True
    ip = _parse_ip(host)
    return ip is not None and ip.is_loopback


def transport_security_for(host: str) -> TransportSecuritySettings:
    """Host and Origin checks for a server bound to `host`.

    On a loopback bind, any loopback name with any port is accepted, so a
    forwarded port keeps working; other names are refused (DNS rebinding).
    On any other bind the REST API on the same port has no such check, so the
    MCP has none either.
    """
    if not is_loopback_host(host):
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    names = list(_LOOPBACK_NAMES)
    bound = _url_host(host)
    if bound not in names:
        names.append(bound)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[entry for name in names for entry in (name, f"{name}:*")],
        allowed_origins=[
            origin
            for name in names
            for origin in (f"http://{name}", f"http://{name}:*")
        ],
    )


def app_origin(host: str, port: int) -> str:
    """The address of the Kiln app for links shown to users, from the bound
    host and port only. A loopback or wildcard bind gives `localhost`, because
    the server cannot know which address a remote user opened."""
    ip = _parse_ip(host)
    is_wildcard = ip is not None and ip.is_unspecified
    if _strip_brackets(host) == "" or is_wildcard or is_loopback_host(host):
        return f"http://localhost:{port}"
    return f"http://{_url_host(host)}:{port}"
