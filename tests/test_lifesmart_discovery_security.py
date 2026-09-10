"""Security-focused tests for LifeSmart local discovery."""

from __future__ import annotations

import asyncio
import socket
from ipaddress import IPv4Address, IPv6Address
from unittest.mock import AsyncMock, Mock

import custom_components.lifesmart.lifesmart_client_local as local_module


def test_discovery_source_ips_use_enabled_home_assistant_ipv4(monkeypatch):
    hass = object()
    monkeypatch.setattr(local_module, "async_get_hass_or_none", lambda: hass)
    get_source_ips = AsyncMock(
        return_value=[
            IPv4Address("192.168.1.10"),
            IPv6Address("fe80::1"),
            IPv4Address("192.168.1.10"),
            IPv4Address("10.0.0.5"),
            IPv4Address("0.0.0.0"),
        ]
    )
    monkeypatch.setattr(
        local_module.network, "async_get_enabled_source_ips", get_source_ips
    )

    source_ips = asyncio.run(local_module._async_get_discovery_source_ips())

    assert source_ips == ["192.168.1.10", "10.0.0.5"]
    get_source_ips.assert_awaited_once_with(hass)


def test_discovery_source_ips_do_not_fall_back_to_wildcard(monkeypatch):
    monkeypatch.setattr(local_module, "async_get_hass_or_none", lambda: None)

    assert asyncio.run(local_module._async_get_discovery_source_ips()) == []


def test_discovery_socket_binds_specific_interface(monkeypatch):
    sockets = []

    class FakeSocket:
        def __init__(self, *args):
            self.options = []
            self.bound = None
            self.closed = False
            sockets.append(self)

        def setblocking(self, value):
            assert value is False

        def setsockopt(self, level, option, value):
            self.options.append((level, option, value))

        def bind(self, address):
            self.bound = address

        def close(self):
            self.closed = True

    transport = Mock()

    class FakeLoop:
        async def create_datagram_endpoint(self, factory, *, sock):
            assert sock is sockets[-1]
            assert isinstance(factory(), local_module._LifeSmartDiscoveryProtocol)
            return transport, Mock()

    monkeypatch.setattr(local_module.socket, "socket", FakeSocket)
    monkeypatch.setattr(local_module.asyncio, "get_running_loop", lambda: FakeLoop())

    result = asyncio.run(
        local_module._async_open_discovery_socket("192.168.1.10", 60021, {})
    )

    assert result is transport
    assert sockets[0].bound == ("192.168.1.10", 60021)
    assert sockets[0].bound[0] not in {"", "0.0.0.0"}
    assert (
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_IF,
        socket.inet_aton("192.168.1.10"),
    ) in sockets[0].options


def test_discovery_transport_fans_out_to_all_enabled_interfaces(monkeypatch):
    first = Mock()
    second = Mock()
    monkeypatch.setattr(
        local_module,
        "_async_get_discovery_source_ips",
        AsyncMock(return_value=["192.168.1.10", "10.0.0.5"]),
    )
    open_socket = AsyncMock(side_effect=[first, second])
    monkeypatch.setattr(local_module, "_async_open_discovery_socket", open_socket)

    transport = asyncio.run(local_module._async_open_discovery_transport(60021, {}))
    destination = (
        local_module.DISCOVERY_BROADCAST_HOST,
        local_module.DISCOVERY_BROADCAST_PORT,
    )
    transport.sendto(local_module.DISCOVERY_SEARCH, destination)
    transport.close()

    assert open_socket.await_args_list[0].args[:2] == ("192.168.1.10", 60021)
    assert open_socket.await_args_list[1].args[:2] == ("10.0.0.5", 60021)
    first.sendto.assert_called_once_with(local_module.DISCOVERY_SEARCH, destination)
    second.sendto.assert_called_once_with(local_module.DISCOVERY_SEARCH, destination)
    first.close.assert_called_once()
    second.close.assert_called_once()
