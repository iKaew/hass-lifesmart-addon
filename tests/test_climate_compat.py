"""Exercise temperature reporting through both supported Home Assistant APIs."""

from types import SimpleNamespace

import pytest
from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.lifesmart.spotac_climate import LifeSmartSPOTACClimate
from tests.test_climate import make_air_device, make_climate_entity, make_thermostat_device
from tests.test_nature_climate import make_entity
from tests.test_spotac_climate_module import FakeClient, make_raw_device


@pytest.mark.parametrize("device", ["air", "thermostat", "nature", "spot"])
@pytest.mark.parametrize("units", [METRIC_SYSTEM, US_CUSTOMARY_SYSTEM])
def test_climate_state_converts_native_temperatures(device, units, caplog):
    if device == "air":
        entity, _, _ = make_climate_entity(make_air_device())
    elif device == "thermostat":
        entity, _, _ = make_climate_entity(make_thermostat_device())
    elif device == "nature":
        entity, _, _ = make_entity()
    else:
        entity = LifeSmartSPOTACClimate(
            None, make_raw_device(), FakeClient(),
            {"category": "ac", "brand": "aux", "idx": "33.irxs"},
        )
    entity.hass = SimpleNamespace(config=SimpleNamespace(units=units))

    assert entity.native_temperature_unit == UnitOfTemperature.CELSIUS
    state = entity.state_attributes
    fahrenheit = units.temperature_unit == UnitOfTemperature.FAHRENHEIT
    expected_targets = {
        "air": (24, 75), "thermostat": (22, 71),
        "nature": (23, 73), "spot": (25, 77),
    }
    expected_current = {
        "air": (22, 72), "thermostat": (20, 68),
        "nature": (22, 71), "spot": (None, None),
    }
    assert state["temperature"] == expected_targets[device][fahrenheit]
    assert state["current_temperature"] == expected_current[device][fahrenheit]
    assert "deprecated" not in caplog.text
