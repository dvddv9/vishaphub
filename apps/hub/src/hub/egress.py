"""Offline mode: this process talks to the private network and to nothing else.

``VISHAP_HUB_OFFLINE=1`` is for an installation whose code must not leave the customer's network. It is
enforced in two places, so a forgotten setting cannot quietly send something out:

* a readable check where the settings are read - a model address on the public internet is refused with the
  sentence that says what to change (``llm.settings``), and the voice (which needs an online service) is off;
* a guard on every outgoing socket connection of the process. A connection to a public address is refused
  before a single packet is sent, whatever library asks for it.

What counts as "inside": loopback, private ranges (10/8, 172.16/12, 192.168/16, fc00::/7) and link-local
addresses, plus whatever ``VISHAP_HUB_ALLOWED_HOSTS`` lists (comma separated IP addresses, networks in CIDR
form or host names - a gateway that lives on a public address but belongs to the company, say).

The guard looks at the address a connection is about to be made to. A name is resolved first and every
address it resolves to has to be inside. Connections that do not use Python's sockets (the Postgres driver
speaks through its own C library) are not seen by the guard; they go where ``VISHAP_HUB_DATABASE_URL``
points, which is the operator's own setting.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

_ON = ("1", "true", "yes", "on")
_original: dict[str, object] = {}


class EgressBlocked(PermissionError):
    """A connection that offline mode does not allow. An OSError, so callers handle it like any refused connection."""


def offline() -> bool:
    return (os.getenv("VISHAP_HUB_OFFLINE") or "").strip().lower() in _ON


def _allowed() -> tuple[list, set]:
    networks, names = [], set()
    for item in (os.getenv("VISHAP_HUB_ALLOWED_HOSTS") or "").split(","):
        item = item.strip().lower()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            names.add(item)
    return networks, names


def _inside(ip: str, networks: list) -> bool:
    try:
        address = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if address.is_loopback or address.is_private or address.is_link_local:
        return True
    return any(address in network for network in networks)


def host_allowed(host: str) -> bool:
    """May a connection to this host or address be made while offline?"""
    host = (host or "").strip().strip("[]").lower()
    if not host:
        return False
    networks, names = _allowed()
    if host in names or host in ("localhost", "host.docker.internal"):
        return True
    try:
        ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        try:
            resolved = {item[4][0] for item in socket.getaddrinfo(host, None)}
        except OSError:
            return False                      # a name that does not resolve is not known to be inside
        return bool(resolved) and all(_inside(ip, networks) for ip in resolved)
    return _inside(host, networks)


def url_allowed(url: str) -> bool:
    """Always True when not offline."""
    if not offline():
        return True
    return host_allowed(urlparse(url).hostname or "")


def _guard(name: str):
    real = _original[name]

    def guarded(self, address, *args, **kwargs):
        if offline() and isinstance(address, tuple) and address:
            if not host_allowed(str(address[0])):
                raise EgressBlocked(
                    f"offline mode: a connection to {address[0]} is refused; only the private network is allowed "
                    "(see VISHAP_HUB_ALLOWED_HOSTS)")
        return real(self, address, *args, **kwargs)

    guarded.__wrapped__ = real
    return guarded


def install() -> None:
    """Put the guard on outgoing connections. Idempotent; it only acts while ``offline()`` is true."""
    if _original:
        return
    for name in ("connect", "connect_ex"):
        _original[name] = getattr(socket.socket, name)
        setattr(socket.socket, name, _guard(name))


def uninstall() -> None:
    """Take the guard off (tests)."""
    for name, real in list(_original.items()):
        setattr(socket.socket, name, real)
        del _original[name]
