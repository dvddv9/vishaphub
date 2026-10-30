"""Loaded as `sitecustomize` by the Python that runs code under test (see safe.network_guard_dir).

Refuses every socket that is not AF_UNIX: connections, DNS, listening. It needs no privilege, so it
works where `unshare -n` does not (a non-root user in a container). It stops requests, urllib,
http.client and plain sockets. It does not stop ctypes, the raw `_socket` module, or a `curl`
subprocess: only a network namespace or `docker run --network none` does.
"""
import socket as _s

_MSG = "network is disabled for code under test"


def _deny(*args, **kwargs):
    raise PermissionError(_MSG)


def _gate(name):
    orig = getattr(_s.socket, name, None)
    if orig is None:
        return

    def wrapper(self, *args, **kwargs):
        if self.family == getattr(_s, "AF_UNIX", object()):
            return orig(self, *args, **kwargs)
        raise PermissionError(_MSG)

    setattr(_s.socket, name, wrapper)


for _name in ("connect", "connect_ex", "bind", "listen", "sendto", "sendmsg"):
    _gate(_name)
for _name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo",
              "create_connection", "create_server"):
    if hasattr(_s, _name):
        setattr(_s, _name, _deny)