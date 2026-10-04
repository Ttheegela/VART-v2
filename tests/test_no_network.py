import socket

import pytest
import pytest_socket


def test_connections_to_non_local_hosts_are_blocked() -> None:
    # --allow-hosts (pyproject addopts) overrides --disable-socket, so the connect guard fires:
    # SocketConnectBlockedError, not SocketBlockedError. pytest-socket also warns when it blocks.
    with (
        pytest.warns(UserWarning, match="93.184.216.34"),
        pytest.raises(pytest_socket.SocketConnectBlockedError),
    ):
        socket.create_connection(("93.184.216.34", 80), timeout=1)
