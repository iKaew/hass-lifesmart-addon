"""Reconnect snapshots must refresh entities without losing newer push data."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.climate.const import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send

from custom_components.lifesmart.recovery import (
    CloudStateRecovery,
    async_apply_device_snapshot,
)
from custom_components.lifesmart.runtime_data import LifeSmartRuntimeData
from tests.test_climate import make_air_device, make_climate_entity
from tests.lifesmart_entity_helpers import make_switch


def test_snapshot_updates_real_entities_and_preserves_registry_metadata(tmp_path):
    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        raw = make_air_device()
        raw["_ha_hub_device_registry_id"] = "registry-id"
        climate, _, _ = make_climate_entity(raw)
        switch = make_switch("SL_SW_IF1", "P1", {"type": 128, "val": 0})
        switch_raw = switch.raw_device_data
        runtime = LifeSmartRuntimeData(
            client=None, devices=[raw, switch_raw],
            device_availability={("HUB1", "AIR1"): True, ("HUB1", "DEVICE1"): True},
        )
        runtime.track_entities([climate, switch])
        for entity in (climate, switch):
            entity.hass = hass
            entity.schedule_update_ha_state = lambda: None
            entity.async_schedule_update_ha_state = lambda: None
        async_dispatcher_connect(hass, "AIR1", climate._update_state)
        async_dispatcher_connect(hass, "DEVICE1", switch._update_state)

        snapshot = deepcopy(raw)
        snapshot.pop("_ha_hub_device_registry_id")
        # Deliberately put mode before power, as API dictionaries aren't ordered
        # according to the dependencies in the entity's incremental handlers.
        snapshot["data"] = {
            "MODE": {"type": 0xCE, "val": 4},
            "O": {"type": 129, "val": 1},
            "tT": {"type": 0x88, "val": 280},
            "T": {"type": 0x08, "val": 250},
        }
        climate._mode = HVACMode.OFF
        await async_apply_device_snapshot(runtime, [snapshot, {
            **switch_raw, "stat": 1, "data": {"P1": {"type": 129, "val": 1}},
        }], lambda message: dispatcher_send(
            hass, message["msg"]["me"], message["msg"]
        ))

        assert climate.native_target_temperature == 28
        assert climate.native_current_temperature == 25
        assert climate.hvac_mode == HVACMode.HEAT
        assert switch.is_on is True
        assert runtime.connected is False
        assert climate.available is False
        assert runtime.devices[0] is raw
        assert raw["data"]["tT"] == {"type": 0x88, "val": 280}
        assert raw["_ha_hub_device_registry_id"] == "registry-id"
        runtime.set_connected(True)
        assert climate.available is True

    asyncio.run(scenario())


def test_snapshot_marks_missing_and_offline_devices_unavailable():
    raw = make_air_device()
    runtime = LifeSmartRuntimeData(
        client=None, devices=[raw],
        device_availability={("HUB1", "AIR1"): True, ("HUB2", "MISSING"): True},
    )
    on_event = Mock()
    asyncio.run(async_apply_device_snapshot(runtime, [{**raw, "stat": 0}], on_event))
    assert runtime.device_availability == {
        ("HUB1", "AIR1"): False, ("HUB2", "MISSING"): False,
    }
    on_event.assert_not_called()


def test_snapshot_distinguishes_device_ids_on_different_hubs():
    first, second = make_air_device(), make_air_device()
    second["agt"] = "HUB2"
    runtime = LifeSmartRuntimeData(client=None, devices=[first, second])
    on_event = Mock()
    asyncio.run(async_apply_device_snapshot(runtime, [{
        **second, "data": {"tT": {"type": 0x88, "val": 280}},
    }], on_event))
    assert first["data"]["tT"] == {"v": 24}
    assert second["data"]["tT"]["val"] == 280
    assert on_event.call_args.args[0]["msg"]["agt"] == "HUB2"


def make_recovery(client, on_event):
    runtime = LifeSmartRuntimeData(
        client=client, devices=[make_air_device()], last_error="disconnected"
    )
    close = Mock()
    hass = SimpleNamespace(
        async_create_task=lambda coro, name: asyncio.create_task(coro, name=name),
        async_add_executor_job=AsyncMock(side_effect=lambda fn: fn()),
    )
    return CloudStateRecovery(hass, runtime, on_event, close), runtime, close


def test_cloud_replays_newer_push_after_snapshot_before_becoming_available():
    async def scenario():
        response = asyncio.get_running_loop().create_future()
        async def fetch():
            return await response
        events = []
        recovery, runtime, close = make_recovery(
            SimpleNamespace(get_all_device_async=fetch),
            lambda event: events.append((runtime.connected, event["msg"]["val"])),
        )
        recovery.connected()
        task = recovery._task
        recovery.event({"type": "io", "msg": {"val": 290}})
        assert events == []
        response.set_result([{
            **make_air_device(), "data": {"tT": {"type": 0x88, "val": 280}},
        }])
        await task
        assert events == [(False, 280), (False, 290)]
        assert runtime.connected is True
        assert runtime.last_error is None
        close.assert_not_called()

    asyncio.run(scenario())


@pytest.mark.parametrize("response", [None, {"code": 10009}, ConnectionError("offline")])
def test_cloud_refresh_failure_stays_unavailable_and_retries_transport(response):
    async def scenario():
        fetch = AsyncMock()
        if isinstance(response, Exception):
            fetch.side_effect = response
        else:
            fetch.return_value = response
        on_event = Mock()
        recovery, runtime, close = make_recovery(
            SimpleNamespace(get_all_device_async=fetch), on_event
        )
        recovery.connected()
        await recovery._task
        assert runtime.connected is False
        assert runtime.last_error is not None
        close.assert_called_once()
        on_event.assert_not_called()

    asyncio.run(scenario())


@pytest.mark.parametrize("unload", [False, True])
def test_cloud_cancels_inflight_refresh_on_disconnect_or_unload(unload):
    async def scenario():
        started = asyncio.Event()
        async def fetch():
            started.set()
            await asyncio.Event().wait()
        on_event = Mock()
        recovery, runtime, close = make_recovery(
            SimpleNamespace(get_all_device_async=fetch), on_event
        )
        recovery.connected()
        task = recovery._task
        await started.wait()
        if unload:
            await recovery.async_close()
            recovery.connected()
        else:
            recovery.disconnected("closed")
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime.connected is False
        assert recovery._task is None
        on_event.assert_not_called()
        close.assert_not_called()

    asyncio.run(scenario())


def test_old_cloud_response_cannot_overwrite_a_new_connection():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0
        async def fetch():
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    # A slow client may finish after cancellation was requested.
                    await release.wait()
                temperature = 240
            else:
                temperature = 280
            return [{**make_air_device(), "data": {"tT": {"type": 136, "val": temperature}}}]
        events = []
        recovery, runtime, _ = make_recovery(
            SimpleNamespace(get_all_device_async=fetch), events.append
        )
        recovery.connected()
        old_task = recovery._task
        await started.wait()
        recovery.disconnected("closed")
        recovery.connected()
        await recovery._task
        release.set()
        await old_task
        assert [event["msg"]["val"] for event in events] == [280]
        assert runtime.connected is True

    asyncio.run(scenario())
