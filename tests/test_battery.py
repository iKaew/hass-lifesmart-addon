"""Missing battery percentages must stay unknown without optional OpenDev."""

import asyncio
from unittest.mock import Mock

import pytest
from homeassistant.const import STATE_UNKNOWN

from custom_components.lifesmart.battery import VOLTAGE_BATTERY_TYPES
from tests.lifesmart_entity_helpers import make_sensor


@pytest.mark.parametrize("device_type", sorted(VOLTAGE_BATTERY_TYPES))
@pytest.mark.parametrize(
    "data",
    [
        {},
        {"val": 150, "rv": 3.0},
        {"val": 137, "rv": 2.74},
        {"v": None, "val": 153, "rv": 3.06},
        {"v": True, "val": 150},
        {"v": "100", "val": 150},
        {"v": -1, "val": 150},
        {"v": 101, "val": 150},
        {"v": float("nan"), "val": 150},
        {"v": float("inf"), "val": 150},
    ],
)
def test_missing_or_invalid_percent_is_ha_unknown_without_opendev(device_type, data):
    entity = make_sensor(device_type, "V", data)
    assert entity.available
    assert entity.state is None
    # Exercise HA's actual serialization, not a literal "N/A" sensor value.
    assert entity._stringify_state(entity.available) == STATE_UNKNOWN
    assert entity.unit_of_measurement == "%"


@pytest.mark.parametrize("device_type", sorted(VOLTAGE_BATTERY_TYPES))
def test_tcp_battery_transitions_between_valid_and_unknown(device_type):
    entity = make_sensor(device_type, "V", {"v": 100, "val": 150})
    entity.schedule_update_ha_state = Mock()
    assert entity.state == 100
    asyncio.run(entity._update_value({"val": 149, "rv": 2.98}))
    assert entity._stringify_state(entity.available) == STATE_UNKNOWN
    asyncio.run(entity._update_value({"v": 0, "val": 100}))
    assert entity.state == 0  # Empty is different from unknown.
    assert entity.schedule_update_ha_state.call_count == 2


def test_documented_temperature_and_humidity_tenths_remain_supported():
    assert make_sensor("SL_SC_BE", "T", {"val": 235}).state == 23.5
    assert make_sensor("SL_SC_BE", "H", {"val": 456}).state == 45.6


def test_door_battery_preserves_low_percentage_instead_of_using_voltage():
    entity = make_sensor("SL_SC_BG", "V", {"v": 6, "val": 137, "rv": 2.74})
    assert entity.state == 6
    assert entity._stringify_state(entity.available) == "6"
