import asyncio
import importlib
import struct

sensor_module = importlib.import_module("custom_components.lifesmart.sensor")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(self, entry_id, devices, exclude_devices=None, exclude_hubs=None, client=None):
        self.data = {
            sensor_module.DOMAIN: {
                entry_id: {
                    "devices": devices,
                    "exclude_devices": exclude_devices or [],
                    "exclude_hubs": exclude_hubs or [],
                    "client": client,
                }
            }
        }


def make_device(device_type, data, device_id="DEV1", hub_id="HUB1"):
    return {
        "name": "Sensor Device",
        "devtype": device_type,
        "agt": hub_id,
        "me": device_id,
        "ver": "1.0",
        "data": data,
    }


def make_sensor_entity(device_type, sub_device_key, sub_device_data):
    raw = make_device(device_type, {sub_device_key: sub_device_data})
    entity = sensor_module.LifeSmartSensor(None, raw, sub_device_key, sub_device_data, client=None)
    updates = []
    entity.schedule_update_ha_state = lambda: updates.append("scheduled")
    return entity, updates


def test_sensor_async_setup_entry_creates_supported_entities():
    ieee = int.from_bytes(struct.pack("!f", 12.5), "big", signed=False)
    devices = [
        make_device("SL_SC_CH", {"P1": {"val": 11}, "P2": {"val": 12}}),
        make_device("SL_LK_LS", {"BAT": {"val": 90}}, device_id="LOCK1"),
        make_device("SL_OE_DE", {"P2": {"v": 1.5}, "P3": {"v": 200}}, device_id="PLUG1"),
        make_device("SL_NATURE", {"P4": {"val": 215}}, device_id="NAT1"),
        make_device("SL_SC_WA", {"V": {"v": 88}}, device_id="WATER1"),
        make_device("SL_SC_CA", {"P1": {"val": 215}, "P2": {"val": 450}, "P3": {"val": 500}, "P4": {"v": 95}}, device_id="CO21"),
        make_device("SL_SC_THL", {"T": {"val": 215}, "H": {"v": 55}, "Z": {"val": 100}, "V": {"v": 80}}, device_id="ENV1"),
        make_device("SL_SC_BM", {"M": {"val": 1}, "V": {"val": 3000, "v": 82}}, device_id="BM1"),
        make_device("SL_SC_CQ", {"P1": {"val": 215}, "P4": {"val": 1200}, "P6": {"v": 3.2}}, device_id="TVOC1"),
        make_device("SL_DF_SR", {"T": {"val": 230}, "V": {"v": 81}}, device_id="DEF1"),
        make_device("ELIQ_EM", {"EPA": {"val": 125}}, device_id="METER1"),
        make_device("V_DLT_645_P", {"EE": {"v": 12}, "EP": {"v": 2}}, device_id="DLT1"),
        make_device("V_485_P", {"EV": {"v": 230}, "PM1": {"val": 50}, "TVOC": {"v": 0.7}, "T": {"val": 215}}, device_id="MOD1"),
        make_device("OD_MFRESH_M8088", {"RM": {"val": 2}, "T": {"val": 215}, "PM": {"val": 22}}, device_id="AIR1"),
        make_device("SL_SC_CN", {"P1": {"val": 50}, "P2": {"val": 20}, "P4": {"val": 30}}, device_id="NOISE1"),
        make_device("SL_SC_CM", {"P3": {"v": 87}}, device_id="CM1"),
        make_device("SL_P_A", {"P2": {"v": 92}}, device_id="SMOKE1"),
    ]
    hass = FakeHass("entry-1", devices, client=object())
    added = []

    asyncio.run(sensor_module.async_setup_entry(hass, FakeConfigEntry(), lambda entities: added.extend(entities)))

    assert len(added) >= 24
    assert any(entity.entity_id == "sensor.sl_sc_ch_hub1_dev1_p1" for entity in added)
    assert any(entity.entity_id == "sensor.sl_lk_ls_hub1_lock1_bat" for entity in added)
    assert any(entity.entity_id == "sensor.sl_sc_bm_hub1_bm1_v" for entity in added)
    assert any(entity.entity_id == "sensor.v_485_p_hub1_mod1_ev" for entity in added)


def test_sensor_entity_branches_and_properties():
    gas, _ = make_sensor_entity("SL_SC_CH", "P1", {"val": 11, "type": 1})
    smart_plug, _ = make_sensor_entity("SL_OE_DE", "P2", {"v": 1.5})
    co2, _ = make_sensor_entity("SL_SC_CA", "P3", {"val": 500})
    env, _ = make_sensor_entity("SL_SC_THL", "T", {"val": 215})
    cube_motion_battery, _ = make_sensor_entity("SL_SC_BM", "V", {"val": 3000, "v": 82})
    tvoc, _ = make_sensor_entity("SL_SC_CQ", "P4", {"val": 1200})
    defed, _ = make_sensor_entity("SL_DF_SR", "V", {"v": 81, "val": 3000})
    noise, _ = make_sensor_entity("SL_SC_CN", "P1", {"val": 50, "type": 1})
    dlt, _ = make_sensor_entity("V_DLT_645_P", "EP", {"v": 2})
    modbus, _ = make_sensor_entity("V_485_P", "CO2PPM", {"v": 400})
    purifier, _ = make_sensor_entity("OD_MFRESH_M8088", "RM", {"val": 2})
    default_temp, _ = make_sensor_entity("SL_NATURE", "P4", {"val": 230})

    assert gas.device_class == sensor_module.SensorDeviceClass.GAS
    assert gas.state == 11
    assert smart_plug.state == 1.5
    assert co2.device_class == sensor_module.SensorDeviceClass.CO2
    assert env.state == 21.5
    assert cube_motion_battery.device_class == sensor_module.SensorDeviceClass.BATTERY
    assert cube_motion_battery.state == 82
    assert cube_motion_battery.extra_state_attributes == {"raw": 3000}
    assert tvoc.state == 1.2
    assert defed.extra_state_attributes == {"raw": 3000}
    assert noise.extra_state_attributes["alarm"] is True
    assert dlt.state == 2
    assert modbus.device_class == sensor_module.SensorDeviceClass.CO2
    assert purifier.state == "fan_2"
    assert purifier._attr_options == list(sensor_module.AIR_PURIFIER_MODES.values())
    assert default_temp.state == 23
    assert gas.unique_id == gas.entity_id
    assert gas.device_info["model"] == "SL_SC_CH"


def test_sensor_update_and_dispatcher_registration(monkeypatch):
    sensor, updates = make_sensor_entity("SL_SC_CH", "P1", {"val": 11, "type": 1})
    sensor.hass = object()
    removers = []
    calls = []

    def fake_connect(hass, signal, callback):
        calls.append((hass, signal, callback))
        return "remove-token"

    sensor.async_on_remove = lambda remover: removers.append(remover)
    monkeypatch.setattr(sensor_module, "async_dispatcher_connect", fake_connect)
    asyncio.run(sensor.async_added_to_hass())
    asyncio.run(sensor._update_value({"val": 22, "type": 0}))
    asyncio.run(sensor._update_value(None))

    assert sensor.state == 2.2
    assert removers == ["remove-token"]
    assert updates == ["scheduled"]


def test_sensor_helper_functions_cover_remaining_paths():
    ieee = int.from_bytes(struct.pack("!f", 12.5), "big", signed=False)

    assert sensor_module._display_value({"v": 1.2}) == 1.2
    assert sensor_module._display_value({"val": 600}, "SL_SC_CA", "P3") == 600
    assert sensor_module._display_value({"val": 100}, "SL_SC_THL", "Z") == 100
    assert sensor_module._display_value({"val": 1200}, "SL_SC_CQ", "P4") == 1.2
    assert sensor_module._display_value({"val": 77}, "ELIQ_EM", "EPA") == 77
    assert sensor_module._display_value({"val": ieee}, "V_DLT_645_P", "EE") == 12.5
    assert sensor_module._display_value({"val": 215}, "V_485_P", "T") == 21.5
    assert sensor_module._display_value({"val": 50}, "V_485_P", "PM") == 50
    assert sensor_module._display_value({"val": 2}, "OD_MFRESH_M8088", "RM") == "fan_2"
    assert sensor_module._display_value({"val": 9}, "SL_LK_LS", "BAT") == 9
    assert sensor_module._display_value({"val": 215}) == 21.5
    assert sensor_module._display_float_value({"val": ieee}) == 12.5
    assert sensor_module._float32_from_int(ieee) == 12.5
    assert sensor_module._is_modbus_sensor_key("EE1") is True
    assert sensor_module._is_modbus_sensor_key("PM10") is True
    assert sensor_module._modbus_sensor_metadata("EPF1")[0] == sensor_module.SensorDeviceClass.POWER_FACTOR
    assert sensor_module._modbus_sensor_metadata("O2VOL")[1] == sensor_module.PERCENTAGE
    assert sensor_module._modbus_sensor_metadata("UNKNOWN") == (None, "None")
    assert sensor_module._state_attributes({"type": 1, "val": 11}, "SL_SC_CH", "P1") == {"alarm": True, "raw": 11}
    assert sensor_module._state_attributes({"type": 1, "val": 50}, "SL_SC_CN", "P1") == {"alarm": True, "raw": 50}
