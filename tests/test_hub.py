import asyncio
from types import SimpleNamespace

import pytest

from custom_components.lifesmart.button import LifeSmartHubRestartButton
from custom_components.lifesmart.const import DOMAIN, HUB_ID_KEY
from custom_components.lifesmart.hub import (
    HUB_STATE_INITIALIZING,
    HUB_STATE_OFFLINE,
    HUB_STATE_ONLINE,
    LifeSmartHubCoordinator,
)
from custom_components.lifesmart.sensor import LifeSmartHubStatusSensor


class FakeCoordinator:
    def __init__(self, data, last_update_success=True):
        self.data = data
        self.last_update_success = last_update_success


class FakeHubClient:
    def __init__(self, states=None, reboot_response=None, reboot_error=None):
        self.states = states or {}
        self.reboot_response = reboot_response or {"code": 0}
        self.reboot_error = reboot_error
        self.reboot_calls = []

    async def get_hub_state_async(self, hub_id):
        result = self.states[hub_id]
        if isinstance(result, BaseException):
            raise result
        return result

    async def reboot_hub_async(self, hub_id):
        self.reboot_calls.append(hub_id)
        if self.reboot_error is not None:
            raise self.reboot_error
        return self.reboot_response


def test_hub_status_sensor_maps_documented_states_and_metadata():
    coordinator = FakeCoordinator({"HUB1": {"state": HUB_STATE_INITIALIZING}})
    sensor = LifeSmartHubStatusSensor(
        coordinator,
        {
            HUB_ID_KEY: "HUB1",
            "ip": "192.168.1.20",
            "mac": "aa:bb:cc:dd:ee:ff",
            "tmzone": 7,
        },
    )

    assert sensor.native_value == "initializing"
    assert sensor.available is True
    assert sensor.unique_id == "HUB1_status"
    assert sensor.device_info == {"identifiers": {(DOMAIN, "HUB1")}}
    assert sensor.extra_state_attributes == {
        "ip_address": "192.168.1.20",
        "mac_address": "aa:bb:cc:dd:ee:ff",
        "time_zone": 7,
    }

    coordinator.data["HUB1"]["state"] = HUB_STATE_OFFLINE
    assert sensor.native_value == "offline"
    coordinator.data["HUB1"]["state"] = HUB_STATE_ONLINE
    assert sensor.native_value == "online"


def test_hub_status_sensor_is_unavailable_without_current_data():
    sensor = LifeSmartHubStatusSensor(
        FakeCoordinator({}, last_update_success=True), {HUB_ID_KEY: "HUB1"}
    )
    failed = LifeSmartHubStatusSensor(
        FakeCoordinator({"HUB1": {"state": HUB_STATE_ONLINE}}, False),
        {HUB_ID_KEY: "HUB1"},
    )

    assert sensor.available is False
    assert sensor.native_value is None
    assert failed.available is False


def test_hub_coordinator_keeps_other_hubs_available_when_one_update_fails():
    client = FakeHubClient(
        states={
            "HUB1": {"state": HUB_STATE_ONLINE},
            "HUB2": RuntimeError("offline"),
            "HUB3": {"code": 500},
        }
    )
    entry = SimpleNamespace(async_on_unload=lambda callback: None)
    coordinator = LifeSmartHubCoordinator(
        SimpleNamespace(),
        entry,
        client,
        [{HUB_ID_KEY: "HUB1"}, {HUB_ID_KEY: "HUB2"}, {HUB_ID_KEY: "HUB3"}],
    )
    data = asyncio.run(coordinator._async_update_data())

    assert data == {"HUB1": {"state": HUB_STATE_ONLINE}}


def test_restart_button_calls_only_its_hub():
    coordinator = FakeCoordinator({"HUB1": {"state": HUB_STATE_ONLINE}})
    client = FakeHubClient()
    button = LifeSmartHubRestartButton(
        coordinator, client, {HUB_ID_KEY: "HUB1"}
    )

    asyncio.run(button.async_press())

    assert client.reboot_calls == ["HUB1"]
    assert button.available is True
    assert button.unique_id == "HUB1_restart"
    assert button.device_info == {"identifiers": {(DOMAIN, "HUB1")}}


@pytest.mark.parametrize(
    ("client", "translation_key"),
    [
        (FakeHubClient(reboot_response={"code": 1}), "hub_restart_rejected"),
        (
            FakeHubClient(reboot_error=RuntimeError("connection failed")),
            "hub_restart_failed",
        ),
    ],
)
def test_restart_button_reports_failures(client, translation_key):
    button = LifeSmartHubRestartButton(
        FakeCoordinator({"HUB1": {"state": HUB_STATE_ONLINE}}),
        client,
        {HUB_ID_KEY: "HUB1"},
    )

    with pytest.raises(Exception) as error:
        asyncio.run(button.async_press())

    assert error.value.translation_key == translation_key
