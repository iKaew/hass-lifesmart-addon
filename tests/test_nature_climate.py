import asyncio
import importlib

from homeassistant.components.climate.const import FAN_HIGH, FAN_LOW, FAN_MEDIUM, ClimateEntityFeature, HVACMode

nature_module = importlib.import_module("custom_components.lifesmart.nature_climate")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(self, entry_id, devices, exclude_devices=None, exclude_hubs=None, client=None):
        self.data = {
            nature_module.DOMAIN: {
                entry_id: {
                    "devices": devices,
                    "exclude_devices": exclude_devices or [],
                    "exclude_hubs": exclude_hubs or [],
                    "client": client,
                }
            }
        }


class FakeDevice:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    async def async_lifesmart_epset(self, type, val, idx):
        self.calls.append((type, val, idx))
        return self.results.pop(0) if self.results else 0


def make_raw_device(device_id="NATURE1"):
    return {
        "name": "Nature",
        "devtype": "SL_NATURE",
        "agt": "HUB1",
        "me": device_id,
        "ver": "1.0",
        "data": {
            "P1": {"type": 1},
            "P2": {"val": 0},
            "P3": {"val": 0},
            "P4": {"val": 215},
            "P6": {"val": 3},
            "P7": {"val": 4},
            "P8": {"val": 230},
            "P9": {"val": 45},
            "P10": {"val": 101},
        },
    }


def make_entity(results=None):
    raw = make_raw_device()
    device = FakeDevice(results)
    entity = nature_module.LifeSmartNatureClimate(device, raw, client=object())
    updates = []
    entity.async_schedule_update_ha_state = lambda: updates.append("scheduled")
    return entity, device, updates


def test_async_setup_entry_filters_nature_thermostats(monkeypatch):
    monkeypatch.setattr(nature_module, "is_nature_thermostat", lambda device: device["me"] == "GOOD")
    devices = [make_raw_device("GOOD"), make_raw_device("BAD")]
    hass = FakeHass("entry-1", devices, client=object())
    added = []

    asyncio.run(nature_module.async_setup_entry(hass, FakeConfigEntry(), lambda entities: added.extend(entities)))

    assert len(added) == 1
    assert added[0].entity_id == "climate.sl_nature_hub1_good_thermostat"


def test_nature_properties_and_setters(monkeypatch):
    async def fake_sleep(seconds):
        pass
    monkeypatch.setattr(nature_module.asyncio, "sleep", fake_sleep)

    entity, device, updates = make_entity(results=[0, 0, 0, 0, 0])

    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.AUTO, HVACMode.FAN_ONLY, HVACMode.COOL, HVACMode.HEAT]
    assert entity.current_temperature == 21.5
    assert entity.target_temperature == 23
    assert entity.fan_mode == "auto"
    assert entity.fan_modes == [FAN_LOW, FAN_MEDIUM, FAN_HIGH, "auto", "off"]
    assert entity.supported_features == (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE)

    asyncio.run(entity.async_set_temperature(temperature=24))
    asyncio.run(entity.async_set_fan_mode(FAN_HIGH))
    asyncio.run(entity.async_set_hvac_mode(HVACMode.OFF))
    asyncio.run(entity.async_set_hvac_mode(HVACMode.COOL))

    assert device.calls == [
        ("0x89", 240, "P8"),
        ("0xCF", 75, "P9"),
        ("0x80", 0, "P1"),
        ("0x81", 1, "P1"),
        ("0xCF", 3, "P7"),
    ]
    assert updates == ["scheduled", "scheduled", "scheduled", "scheduled"]


def test_nature_hvac_from_off_update_state_and_helpers(monkeypatch):
    sleep_calls = []
    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
    monkeypatch.setattr(nature_module.asyncio, "sleep", fake_sleep)

    entity, device, updates = make_entity(results=[0, 0])
    entity._mode = HVACMode.OFF
    asyncio.run(entity.async_set_hvac_mode(HVACMode.AUTO))
    asyncio.run(entity._update_state({"idx": "P1", "type": 1}))
    asyncio.run(entity._update_state({"idx": "P4", "val": 210}))
    asyncio.run(entity._update_state({"idx": "P7", "val": 2}))
    asyncio.run(entity._update_state({"idx": "P8", "val": 225}))
    asyncio.run(entity._update_state({"idx": "P9", "val": 15}))
    asyncio.run(entity._update_state({"idx": "P10", "val": 0}))

    assert device.calls == [("0x81", 1, "P1"), ("0xCF", 1, "P7")]
    assert sleep_calls == [1]
    assert entity.hvac_mode == HVACMode.FAN_ONLY
    assert entity.current_temperature == 21
    assert entity.target_temperature == 22.5
    assert entity.fan_mode == "off"
    assert len(updates) == 7
    assert nature_module._get_fan_mode(None) is None
    assert nature_module._get_fan_mode(15) == FAN_LOW
    assert nature_module._get_nature_fan_mode(101) == "auto"
    assert nature_module._get_nature_fan_speed("off") == 0
    assert nature_module._nature_mode_from_value(99) == HVACMode.AUTO
    assert nature_module._nature_mode_to_value(HVACMode.HEAT) == 4
    assert nature_module._temperature_value(None, 215) == 21.5


def test_nature_async_added_to_hass_registers_dispatcher(monkeypatch):
    entity, _device, _updates = make_entity()
    entity.hass = object()
    removers = []
    calls = []

    def fake_connect(hass, signal, callback):
        calls.append((hass, signal, callback))
        return "remove-token"

    entity.async_on_remove = lambda remover: removers.append(remover)
    monkeypatch.setattr(nature_module, "async_dispatcher_connect", fake_connect)
    asyncio.run(entity.async_added_to_hass())
    assert calls[0][1] == f"{nature_module.LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity.entity_id}"
    assert removers == ["remove-token"]
