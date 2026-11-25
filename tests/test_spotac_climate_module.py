import asyncio
import importlib
from types import SimpleNamespace

import pytest

from homeassistant.components.climate.const import HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

spotac_module = importlib.import_module("custom_components.lifesmart.spotac_climate")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1", data=None, options=None):
        self.entry_id = entry_id
        self.data = data or {}
        self.options = options or {}


class FakeHass:
    def __init__(self, entry_id, devices, client=None):
        self.data = {
            spotac_module.DOMAIN: {
                entry_id: {
                    "devices": devices,
                    "exclude_devices": [],
                    "exclude_hubs": [],
                    "client": client,
                }
            }
        }


class FakeClient:
    def __init__(self, ac_codes=None):
        self.ac_codes = ac_codes
        self.get_calls = []
        self.send_calls = []

    async def get_ac_codes_async(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.ac_codes

    async def send_ir_code_async(self, hub_id, device_id, ir_code):
        self.send_calls.append((hub_id, device_id, ir_code))
        return {"code": 0}


def make_raw_device(device_id="SPOT1"):
    return {
        "name": "Spot",
        "devtype": "SL_SPOT",
        "agt": "HUB1",
        "me": device_id,
        "ver": "1.0",
    }


def test_spotac_async_setup_entry_creates_only_ac_configured_spots():
    devices = [make_raw_device("SPOT1"), make_raw_device("SPOT2")]
    entry = FakeConfigEntry(
        data={},
        options={spotac_module.CONF_AC_CONFIG: {"HUB1_SPOT1": {"category": spotac_module.IR_CATEGORY_AC, "brand": "aux", "idx": "33.irxs"}}},
    )
    hass = FakeHass(entry.entry_id, devices, client=FakeClient())
    added = []

    asyncio.run(spotac_module.async_setup_entry(hass, entry, lambda entities: added.extend(entities)))

    assert len(added) == 1
    assert added[0]._attr_suggested_object_id == "sl_spot_hub1_spot1_climate_ac"


def test_spotac_entity_controls_and_send_command_paths():
    client = FakeClient(ac_codes={"data": "IR"})
    entity = spotac_module.LifeSmartSPOTACClimate(None, make_raw_device(), client, {"category": "ac", "brand": "aux", "idx": "33.irxs"})
    writes = []
    entity.async_write_ha_state = lambda: writes.append("write")
    assert entity.native_temperature_unit == UnitOfTemperature.CELSIUS
    assert entity.native_target_temperature == 25

    asyncio.run(entity.async_turn_on())
    asyncio.run(entity.async_set_hvac_mode(HVACMode.HEAT))
    asyncio.run(entity.async_set_temperature(temperature=26))
    assert entity.native_target_temperature == 26
    asyncio.run(entity.async_set_target_temperature(temperature=24))
    asyncio.run(entity.async_set_fan_mode("Speed 2"))
    asyncio.run(entity.async_set_swing_mode("Direction 3"))
    asyncio.run(entity.async_turn_off())

    assert entity.unique_id.endswith("_ac_aux")
    assert entity.device_info["model"] == "SL_SPOT"
    assert client.send_calls
    assert len(writes) == 7
    assert [call["temp"] for call in client.get_calls] == [25, 25, 26, 24, 24, 24, 24]


def test_spotac_restore_and_send_command_variants(monkeypatch):
    client = FakeClient(ac_codes=[{"data": "LIST_IR"}])
    entity = spotac_module.LifeSmartSPOTACClimate(None, make_raw_device(), client, {"category": "ac", "brand": "aux", "idx": "33.irxs"})
    entity.async_write_ha_state = lambda: None
    entity.hass = SimpleNamespace(config=SimpleNamespace(units=METRIC_SYSTEM))

    class FakeLastState:
        state = HVACMode.HEAT
        attributes = {"temperature": 27, "fan_mode": "Speed 1", "swing_mode": "Direction 4"}

    async def fake_get_last_state():
        return FakeLastState()

    entity.async_get_last_state = fake_get_last_state
    asyncio.run(entity.async_added_to_hass())
    assert entity._attr_hvac_mode == HVACMode.HEAT
    assert entity.native_target_temperature == 27

    asyncio.run(entity._send_ac_command("power", 0, 1, 25, 0, 0))
    client.ac_codes = "STR_IR"
    asyncio.run(entity._send_ac_command("power", 0, 1, 25, 0, 0))
    client.ac_codes = {"codes": [{"data": "NESTED_IR"}]}
    asyncio.run(entity._send_ac_command("power", 0, 1, 25, 0, 0))
    client.ac_codes = {"power": {"data": "KEY_IR"}}
    asyncio.run(entity._send_ac_command("power", 0, 1, 25, 0, 0))
    client.ac_codes = {"POWER": {"data": "UPPER_IR"}}
    asyncio.run(entity._send_ac_command("power", 0, 1, 25, 0, 0))

    bad_entity = spotac_module.LifeSmartSPOTACClimate(None, make_raw_device("SPOT2"), client, {"category": "bad", "brand": "aux", "idx": "33.irxs"})
    asyncio.run(bad_entity._send_ac_command("power", 0, 1, 25, 0, 0))
    missing_entity = spotac_module.LifeSmartSPOTACClimate(None, make_raw_device("SPOT3"), client, {"category": "ac", "brand": "", "idx": ""})
    asyncio.run(missing_entity._send_ac_command("power", 0, 1, 25, 0, 0))

    assert [call[2] for call in client.send_calls] == ["LIST_IR", "STR_IR", "NESTED_IR", "KEY_IR", "UPPER_IR"]


@pytest.mark.parametrize("stored_temperature,stored_unit,system", [
    (27, UnitOfTemperature.CELSIUS, US_CUSTOMARY_SYSTEM),
    (80.6, UnitOfTemperature.FAHRENHEIT, METRIC_SYSTEM),
    (80.6, None, US_CUSTOMARY_SYSTEM),
    (27, None, METRIC_SYSTEM),
])
def test_spotac_restores_native_temperature_before_sending_commands(
    stored_temperature, stored_unit, system
):
    client = FakeClient(ac_codes={"data": "IR"})
    entity = spotac_module.LifeSmartSPOTACClimate(
        None, make_raw_device(), client,
        {"category": "ac", "brand": "aux", "idx": "33.irxs"},
    )
    entity.hass = SimpleNamespace(config=SimpleNamespace(units=system))
    entity.async_write_ha_state = lambda: None
    attributes = {"temperature": stored_temperature}
    if stored_unit is not None:
        attributes["temperature_unit"] = stored_unit

    async def last_state():
        return SimpleNamespace(state=HVACMode.COOL, attributes=attributes)

    entity.async_get_last_state = last_state
    asyncio.run(entity.async_added_to_hass())
    assert entity.native_target_temperature == 27
    asyncio.run(entity.async_turn_on())
    assert client.get_calls[0]["temp"] == 27
