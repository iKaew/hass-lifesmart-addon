"""Synthetic OpenDev protocol and battery-source regression coverage."""

import asyncio
import copy
import json
import socket
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.lifesmart import opendev
from custom_components.lifesmart.runtime_data import LifeSmartRuntimeData
from custom_components.lifesmart.sensor import (
    LifeSmartOpenDevBatterySensor,
    _display_value,
)
from tests.lifesmart_entity_helpers import make_raw_device, make_sensor


def device(value=100, me="DEVICE1", **changes):
    return {
        "me": me,
        "agt": "HUB1",
        "devtype": "SL_SC_BE",
        "stat": 1,
        "data": {"V": {"v": value, "valts": 1700000000000}},
        **changes,
    }


def packet(body, kind=2):
    encoded = json.dumps(body).encode()
    return struct.pack(">2sHHI", b"JL", 0, kind, len(encoded)) + encoded


@pytest.mark.parametrize(
    "value", [None, True, False, "100", -1, 101, float("nan"), float("inf")]
)
def test_voltage_and_invalid_values_are_never_percentages(value):
    for typ in ["SL_SC_WA", "SL_SC_BE"]:
        assert _display_value({"val": 150, "rv": 3.0}, typ, "V") is None
        assert _display_value({"v": value, "val": 150}, typ, "V") is None
    assert (
        opendev.parse_batteries([device(value)], {"DEVICE1": "SL_SC_BE"}, "HUB1") == {}
    )


@pytest.mark.parametrize("value", [0, 15.5, 100])
def test_valid_percentages_keep_original_report_time(value):
    result = opendev.parse_batteries([device(value)], {"DEVICE1": "SL_SC_BE"}, "HUB1")
    assert result == {
        "DEVICE1": {"percentage": value, "reported_at": "2023-11-14T22:13:20+00:00"}
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"agt": "OTHER"},
        {"devtype": "SL_SC_WA"},
        {"stat": 0},
        {"data": None},
        {"data": {"V": {"val": 150}}},
    ],
)
def test_mismatched_offline_or_missing_friendly_values_are_unavailable(changes):
    assert (
        opendev.parse_batteries([device(**changes)], {"DEVICE1": "SL_SC_BE"}, "HUB1")
        == {}
    )


def test_duplicate_device_is_rejected_and_partial_failure_is_isolated():
    devices = [device(100), device(80, me="DEVICE2"), device(20)]
    result = opendev.parse_batteries(
        devices, {"DEVICE1": "SL_SC_BE", "DEVICE2": "SL_SC_BE"}, "HUB1"
    )
    assert set(result) == {"DEVICE2"}
    assert result["DEVICE2"]["percentage"] == 80


def test_response_must_match_request_hub_framing_and_message_type():
    body = {"id": 7, "agtid": "HUB1", "code": 0, "msg": [device()]}
    assert opendev.decode_response(packet(body), 7, "HUB1") == [device()]
    for wrong in [
        packet(body)[:-1],
        packet(body, 3),
        b"JL",
        packet({**body, "id": 8}),
        packet({**body, "agtid": "OTHER"}),
        packet([1, 2]),
    ]:
        assert opendev.decode_response(wrong, 7, "HUB1") is None
    for changes in [{"code": 102}, {"msg": {}}]:
        with pytest.raises(UpdateFailed):
            opendev.decode_response(packet({**body, **changes}), 7, "HUB1")


def test_real_udp_transport_is_read_only_filters_peer_and_closes(monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
            server.bind(("127.0.0.1", 0))
            server.setblocking(False)
            monkeypatch.setattr(opendev, "OPENDEV_PORT", server.getsockname()[1])
            client = opendev.OpenDevClient("127.0.0.1", "OD_TEST", "test-only", "HUB1")
            task = asyncio.create_task(client.async_get_devices())
            data, peer = await loop.sock_recvfrom(server, 65535)
            assert struct.unpack(">2sHHI", data[:10])[:3] == (b"JL", 0, 1)
            body = json.loads(data[10:])
            assert body["obj"] == "eps" and body["args"] == {}
            assert body["sys"]["model"] == "OD_TEST"
            assert "test-only" not in data[10:].decode()
            response = {"id": body["id"], "agtid": "HUB1", "code": 0, "msg": [device()]}
            # A packet from a different peer must not satisfy the request.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as stranger:
                stranger.sendto(packet({**response, "msg": []}), peer)
            await loop.sock_sendto(server, packet({**response, "id": -1}), peer)
            await loop.sock_sendto(server, packet(response), peer)
            assert await task == [device()]
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reclaimed:
                reclaimed.bind(peer)

    asyncio.run(run())


def test_udp_cancellation_releases_socket(monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
            server.bind(("127.0.0.1", 0))
            server.setblocking(False)
            monkeypatch.setattr(opendev, "OPENDEV_PORT", server.getsockname()[1])
            task = asyncio.create_task(
                opendev.OpenDevClient(
                    "127.0.0.1", "OD_TEST", "test-only", "HUB1"
                ).async_get_devices()
            )
            _, peer = await loop.sock_recvfrom(server, 65535)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reclaimed:
                reclaimed.bind(peer)

    asyncio.run(run())


def test_sensor_keeps_identity_ignores_tcp_and_tracks_failure_recovery():
    raw = make_raw_device("SL_SC_BE")
    observation = {"percentage": 100, "reported_at": "2023-11-14T22:13:20+00:00"}
    coordinator = SimpleNamespace(
        data={"DEVICE1": observation}, last_update_success=True
    )
    entity = LifeSmartOpenDevBatterySensor(
        None, raw, "V", {"val": 150, "rv": 3}, None, coordinator
    )
    original = make_sensor("SL_SC_BE", "V", {"val": 150, "rv": 3})
    assert entity.unique_id == original.unique_id
    assert entity.device_info == original.device_info
    assert not entity.should_poll  # Only the five-minute coordinator polls.
    runtime = LifeSmartRuntimeData(client=None, devices=[raw], connected=True)
    runtime.track_entities([entity])
    assert entity.state == 100 and entity.available
    old_attrs = copy.deepcopy(entity.extra_state_attributes)
    asyncio.run(entity._update_value({"val": 140, "rv": 2.8}))
    assert entity.state == 100 and entity.extra_state_attributes == old_attrs
    coordinator.last_update_success = False
    assert not entity.available and entity.state is None
    coordinator.last_update_success = True
    coordinator.data = {}
    assert not entity.available and entity.state is None
    coordinator.data = {"DEVICE1": {**observation, "percentage": 98}}
    assert entity.available and entity.state == 98
    runtime.connected = False
    assert not entity.available


def test_coordinator_replaces_missing_batteries_and_propagates_failure():
    client = SimpleNamespace(
        hub_id="HUB1", async_get_devices=AsyncMock(return_value=[device()])
    )
    coordinator = object.__new__(opendev.OpenDevBatteryCoordinator)
    coordinator.client = client
    coordinator.targets = {"DEVICE1": "SL_SC_BE"}
    assert asyncio.run(coordinator._async_update_data())["DEVICE1"]["percentage"] == 100
    client.async_get_devices.return_value = []
    assert asyncio.run(coordinator._async_update_data()) == {}
    client.async_get_devices.side_effect = UpdateFailed("unavailable")
    with pytest.raises(UpdateFailed):
        asyncio.run(coordinator._async_update_data())


def test_platform_preserves_existing_entities_and_registers_only_coordinator(
    monkeypatch,
):
    from custom_components.lifesmart import sensor as module
    from tests.test_sensor_module import make_device

    raw = make_device(
        "SL_SC_BE", {"V": {"val": 150}, "T": {"val": 231}}, device_id="DEVICE1"
    )
    client = SimpleNamespace(is_local=True, host="192.0.2.10", hub_id="HUB1")
    runtime = LifeSmartRuntimeData(client=client, devices=[raw], connected=True)
    entry = SimpleNamespace(
        options={
            "opendev_enabled": True,
            "opendev_model": "OD_TEST",
            "opendev_token": "test-token",
        },
        runtime_data=runtime,
    )
    listeners = []
    coordinator = SimpleNamespace(
        data={"DEVICE1": {"percentage": 100, "reported_at": None}},
        last_update_success=True,
        async_refresh=AsyncMock(),
        async_request_refresh=AsyncMock(),
    )

    def listen(callback):
        listeners.append(callback)
        return lambda: listeners.remove(callback)

    coordinator.async_add_listener = listen
    monkeypatch.setattr(module, "OpenDevBatteryCoordinator", lambda *args: coordinator)
    added = []
    asyncio.run(module.async_setup_entry(object(), entry, added.extend))
    assert len(added) == 2
    battery = next(x for x in added if x.sub_device_key == "V")
    temperature = next(x for x in added if x.sub_device_key == "T")
    assert battery.state == 100 and temperature.state == 23.1
    assert isinstance(battery, LifeSmartOpenDevBatterySensor)
    assert not isinstance(temperature, LifeSmartOpenDevBatterySensor)
    removals = []
    battery.async_on_remove = removals.append
    asyncio.run(battery.async_added_to_hass())
    assert len(listeners) == 1
    removals[0]()
    assert listeners == []
    asyncio.run(battery.async_update())
    coordinator.async_request_refresh.assert_awaited_once()


def test_udp_timeout_closes_socket(monkeypatch):
    async def run():
        loop = asyncio.get_running_loop()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
            server.bind(("127.0.0.1", 0))
            server.setblocking(False)
            monkeypatch.setattr(opendev, "OPENDEV_PORT", server.getsockname()[1])
            task = asyncio.create_task(
                opendev.OpenDevClient(
                    "127.0.0.1", "OD_TEST", "test-only", "HUB1"
                ).async_get_devices()
            )
            _, peer = await loop.sock_recvfrom(server, 65535)
            with pytest.raises(UpdateFailed):
                await task
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reclaimed:
                reclaimed.bind(peer)

    asyncio.run(run())
