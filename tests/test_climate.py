import asyncio
import importlib

from homeassistant.components.climate.const import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntityFeature,
    HVACMode,
)

climate_module = importlib.import_module("custom_components.lifesmart.climate")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(self, entry_id, devices, exclude_devices=None, exclude_hubs=None, client=None):
        self.data = {
            climate_module.DOMAIN: {
                entry_id: {
                    "devices": devices,
                    "exclude_devices": exclude_devices or [],
                    "exclude_hubs": exclude_hubs or [],
                    "client": client,
                }
            }
        }


class FakeLifeSmartDevice:
    def __init__(self, raw_device_data, client, epset_results=None):
        self.raw_device_data = raw_device_data
        self.client = client
        self.epset_results = list(epset_results or [])
        self.epset_calls = []

    async def async_lifesmart_epset(self, type, val, idx):
        self.epset_calls.append((type, val, idx))
        if self.epset_results:
            return self.epset_results.pop(0)
        return 0


def make_air_device(device_id="AIR1"):
    return {
        "name": "Air",
        "devtype": climate_module.AIR_TYPES[0],
        "agt": "HUB1",
        "me": device_id,
        "ver": "1.0",
        "data": {
            "O": {"type": 1},
            "MODE": {"val": 3},
            "F": {"val": 45},
            "tT": {"v": 24},
            "T": {"v": 22},
        },
    }


def make_thermostat_device(device_id="THERM1"):
    return {
        "name": "Thermostat",
        "devtype": climate_module.THER_TYPES[0],
        "agt": "HUB1",
        "me": device_id,
        "ver": "1.0",
        "data": {
            "P1": {"type": 1},
            "P2": {"type": 0},
            "P3": {"val": 215},
            "P4": {"val": 198},
        },
    }


def make_climate_entity(raw_device, epset_results=None):
    fake_device = FakeLifeSmartDevice(raw_device, client=object(), epset_results=epset_results)
    entity = climate_module.LifeSmartClimateDevice(fake_device, raw_device, client=object())
    updates = []
    entity.async_schedule_update_ha_state = lambda: updates.append("scheduled")
    return entity, fake_device, updates


def test_async_setup_entry_filters_devices_and_adds_supported_climates(monkeypatch):
    spot_calls = []
    nature_calls = []

    async def fake_spot_setup(hass, config_entry, async_add_entities):
        spot_calls.append(config_entry.entry_id)

    async def fake_nature_setup(hass, config_entry, async_add_entities):
        nature_calls.append(config_entry.entry_id)

    monkeypatch.setattr(climate_module, "async_setup_spotac_entry", fake_spot_setup)
    monkeypatch.setattr(climate_module, "async_setup_nature_entry", fake_nature_setup)

    devices = [
        make_air_device("AIR1"),
        make_thermostat_device("THERM1"),
        {"name": "Bad Air", "devtype": climate_module.AIR_TYPES[0], "agt": "HUB1", "me": "BAD", "ver": "1.0", "data": {"O": {"type": 1}}},
        {"name": "Switch", "devtype": "SL_OL", "agt": "HUB1", "me": "SKIP", "ver": "1.0", "data": {}},
        make_air_device("EXCLUDED_DEVICE"),
        dict(make_thermostat_device("EXCLUDED_HUB"), agt="HUBX"),
    ]
    hass = FakeHass(
        "entry-1",
        devices,
        exclude_devices=["EXCLUDED_DEVICE"],
        exclude_hubs=["HUBX"],
        client=object(),
    )
    config_entry = FakeConfigEntry()
    added_entities = []

    asyncio.run(
        climate_module.async_setup_entry(
            hass, config_entry, lambda entities: added_entities.extend(entities)
        )
    )

    assert spot_calls == ["entry-1"]
    assert nature_calls == ["entry-1"]
    assert len(added_entities) == 2
    assert {entity.entity_id for entity in added_entities} == {
        "climate." + f"{make_air_device('AIR1')['devtype']}_hub1_air1".lower(),
        "climate." + f"{make_thermostat_device('THERM1')['devtype']}_hub1_therm1".lower(),
    }


def test_async_setup_platform_handles_none_incomplete_and_valid_discovery():
    added_entities = []

    asyncio.run(climate_module.async_setup_platform(None, None, added_entities.extend, None))
    asyncio.run(climate_module.async_setup_platform(None, None, added_entities.extend, {"dev": None, "param": object()}))
    asyncio.run(climate_module.async_setup_platform(None, None, added_entities.extend, {"dev": {"devtype": climate_module.AIR_TYPES[0], "data": {}}, "param": object()}))
    asyncio.run(climate_module.async_setup_platform(None, None, added_entities.extend, {"dev": make_air_device("AIR2"), "param": object()}))

    assert len(added_entities) == 1
    assert added_entities[0].name == "Air"


def test_air_climate_initialization_and_properties():
    entity, _device, _updates = make_climate_entity(make_air_device())

    assert entity.unique_id == entity.entity_id
    assert entity.name == "Air"
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.hvac_modes == climate_module.LIFESMART_STATE_LIST
    assert entity.current_temperature == 22
    assert entity.target_temperature == 24
    assert entity.min_temp == 10
    assert entity.max_temp == 35
    assert entity.fan_mode == FAN_MEDIUM
    assert entity.fan_modes == climate_module.FAN_MODES
    assert entity.supported_features == (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )
    assert entity.device_info["model"] == make_air_device()["devtype"]
    assert entity._attributes["last_mode"] == HVACMode.COOL


def test_thermostat_initialization_and_properties():
    entity, _device, _updates = make_climate_entity(make_thermostat_device())

    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.hvac_modes == climate_module.LIFESMART_STATE_LIST2
    assert entity.current_temperature == 19.8
    assert entity.target_temperature == 21.5
    assert entity.min_temp == 5
    assert entity.max_temp == 35
    assert entity.fan_mode is None
    assert entity.fan_modes is None
    assert entity.supported_features == ClimateEntityFeature.TARGET_TEMPERATURE
    assert entity._attributes["Heating"] == "false"


def test_async_set_temperature_and_fan_mode_update_state_when_successful():
    air_entity, air_device, air_updates = make_climate_entity(make_air_device(), epset_results=[0, 0])
    therm_entity, therm_device, therm_updates = make_climate_entity(make_thermostat_device(), epset_results=[0])

    asyncio.run(air_entity.async_set_temperature(temperature=25))
    asyncio.run(therm_entity.async_set_temperature(temperature=23))
    asyncio.run(air_entity.async_set_fan_mode(FAN_HIGH))
    asyncio.run(air_entity.async_set_temperature())

    assert air_device.epset_calls == [("0x88", 250, "tT"), ("0xCE", 75, "F")]
    assert therm_device.epset_calls == [("0x88", 230, "P3")]
    assert air_entity.target_temperature == 25
    assert therm_entity.target_temperature == 23
    assert air_entity.fan_mode == FAN_HIGH
    assert air_updates == ["scheduled", "scheduled"]
    assert therm_updates == ["scheduled"]


def test_async_set_hvac_mode_for_air_and_thermostat(monkeypatch):
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(climate_module.asyncio, "sleep", fake_sleep)

    air_off_entity, air_off_device, air_off_updates = make_climate_entity(make_air_device(), epset_results=[0])
    air_off_entity._mode = HVACMode.HEAT
    asyncio.run(air_off_entity.async_set_hvac_mode(HVACMode.OFF))

    air_from_off_entity, air_from_off_device, air_from_off_updates = make_climate_entity(make_air_device(), epset_results=[0, 0])
    air_from_off_entity._mode = HVACMode.OFF
    asyncio.run(air_from_off_entity.async_set_hvac_mode(HVACMode.DRY))

    air_fail_entity, air_fail_device, air_fail_updates = make_climate_entity(make_air_device(), epset_results=[1])
    air_fail_entity._mode = HVACMode.OFF
    asyncio.run(air_fail_entity.async_set_hvac_mode(HVACMode.HEAT))

    therm_off_entity, therm_off_device, therm_off_updates = make_climate_entity(make_thermostat_device(), epset_results=[0, 0])
    asyncio.run(therm_off_entity.async_set_hvac_mode(HVACMode.OFF))

    therm_heat_entity, therm_heat_device, therm_heat_updates = make_climate_entity(make_thermostat_device(), epset_results=[0])
    therm_heat_entity._mode = HVACMode.OFF
    asyncio.run(therm_heat_entity.async_set_hvac_mode(HVACMode.HEAT))

    therm_fail_entity, therm_fail_device, therm_fail_updates = make_climate_entity(make_thermostat_device(), epset_results=[1])
    therm_fail_entity._mode = HVACMode.OFF
    asyncio.run(therm_fail_entity.async_set_hvac_mode(HVACMode.HEAT))

    assert air_off_device.epset_calls == [("0x80", 0, "O")]
    assert air_off_entity.hvac_mode == HVACMode.OFF
    assert air_off_updates == ["scheduled"]

    assert air_from_off_device.epset_calls == [("0x81", 1, "O"), ("0xCE", climate_module.LIFESMART_STATE_LIST.index(HVACMode.DRY), "MODE")]
    assert air_from_off_entity.hvac_mode == HVACMode.DRY
    assert air_from_off_entity._last_mode == HVACMode.DRY
    assert air_from_off_updates == ["scheduled"]

    assert air_fail_device.epset_calls == [("0x81", 1, "O")]
    assert air_fail_entity.hvac_mode == HVACMode.OFF
    assert air_fail_updates == []

    assert therm_off_device.epset_calls == [("0x80", 0, "P1"), ("0x80", 0, "P2")]
    assert therm_off_entity.hvac_mode == HVACMode.OFF
    assert therm_off_updates == ["scheduled"]

    assert therm_heat_device.epset_calls == [("0x81", 1, "P1")]
    assert therm_heat_entity.hvac_mode == HVACMode.HEAT
    assert therm_heat_updates == ["scheduled"]

    assert therm_fail_device.epset_calls == [("0x81", 1, "P1")]
    assert therm_fail_entity.hvac_mode == HVACMode.OFF
    assert therm_fail_updates == []
    assert sleep_calls == [2, 1, 2]


def test_update_state_handles_air_and_thermostat_events():
    air_entity, _air_device, air_updates = make_climate_entity(make_air_device())
    air_entity._mode = HVACMode.OFF
    air_entity._last_mode = HVACMode.HEAT

    for data in [
        {"idx": "O", "type": 1},
        {"idx": "MODE", "type": 0xCE, "val": 5},
        {"idx": "F", "type": 0xCE, "val": 80},
        {"idx": "tT", "type": 0x88, "val": 265},
        {"idx": "T", "type": 0x08, "v": 23},
    ]:
        asyncio.run(air_entity._update_state(data))

    therm_entity, _therm_device, therm_updates = make_climate_entity(make_thermostat_device())
    for data in [
        {"idx": "P1", "type": 0},
        {"idx": "P2", "type": 1},
        {"idx": "P3", "type": 0x88, "val": 230},
        {"idx": "P4", "type": 0x09, "val": 215},
    ]:
        asyncio.run(therm_entity._update_state(data))

    assert air_entity.hvac_mode == HVACMode.DRY
    assert air_entity._last_mode == HVACMode.DRY
    assert air_entity.fan_mode == FAN_HIGH
    assert air_entity.target_temperature == 26.5
    assert air_entity.current_temperature == 23
    assert len(air_updates) == 5

    assert therm_entity.hvac_mode == HVACMode.OFF
    assert therm_entity._attributes["Heating"] == "true"
    assert therm_entity.target_temperature == 23
    assert therm_entity.current_temperature == 21.5
    assert len(therm_updates) == 4


def test_async_added_to_hass_registers_dispatcher_callback(monkeypatch):
    entity, _device, _updates = make_climate_entity(make_air_device())
    entity.hass = object()
    removers = []
    dispatcher_calls = []

    def fake_connect(hass, signal, callback):
        dispatcher_calls.append((hass, signal, callback))
        return "remove-token"

    entity.async_on_remove = lambda remover: removers.append(remover)
    monkeypatch.setattr(climate_module, "async_dispatcher_connect", fake_connect)

    asyncio.run(entity.async_added_to_hass())

    assert dispatcher_calls[0][0] is entity.hass
    assert dispatcher_calls[0][1] == f"{climate_module.LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity.entity_id}"
    assert dispatcher_calls[0][2] == entity._update_state
    assert removers == ["remove-token"]


def test_climate_helper_functions():
    assert climate_module._get_fan_mode(None) is None
    assert climate_module._get_fan_mode(15) == FAN_LOW
    assert climate_module._get_fan_mode(45) == FAN_MEDIUM
    assert climate_module._get_fan_mode(75) == FAN_HIGH

    assert climate_module.LifeSmartClimateDevice._mode_from_mode_value(None) == HVACMode.AUTO
    assert climate_module.LifeSmartClimateDevice._mode_from_mode_value(-1) == HVACMode.AUTO
    assert climate_module.LifeSmartClimateDevice._mode_from_mode_value(99) == HVACMode.AUTO
    assert climate_module.LifeSmartClimateDevice._mode_from_mode_value(4) == HVACMode.HEAT

    air = make_air_device()
    therm = make_thermostat_device()
    assert climate_module._has_required_climate_data(air) is True
    assert climate_module._has_required_climate_data(therm) is True
    assert climate_module._has_required_climate_data({"devtype": climate_module.AIR_TYPES[0], "data": {"O": {"type": 1}}}) is False
    assert climate_module._has_required_climate_data({"devtype": climate_module.THER_TYPES[0], "data": {"P1": {"type": 1}}}) is False
    assert climate_module._temperature_value(22, 210) == 22
    assert climate_module._temperature_value(None, 215) == 21.5
    assert climate_module._temperature_value(None, None) is None


def test_mode_from_air_data_uses_power_state():
    entity, _device, _updates = make_climate_entity(make_air_device())

    assert entity._mode_from_air_data({"O": {"type": 0}, "MODE": {"val": 4}}) == HVACMode.OFF
    assert entity._mode_from_air_data({"O": {"type": 1}, "MODE": {"val": 4}}) == HVACMode.HEAT
