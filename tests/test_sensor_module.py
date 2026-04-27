import asyncio
import importlib
import struct

sensor_module = importlib.import_module("custom_components.lifesmart.sensor")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(
        self, entry_id, devices, exclude_devices=None, exclude_hubs=None, client=None
    ):
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
    entity = sensor_module.LifeSmartSensor(
        None, raw, sub_device_key, sub_device_data, client=None
    )
    updates = []
    entity.schedule_update_ha_state = lambda: updates.append("scheduled")
    return entity, updates


def test_sensor_async_setup_entry_creates_supported_entities():
    devices = [
        make_device("SL_SC_CH", {"P1": {"val": 11}, "P2": {"val": 12}}),
        make_device(
            "SL_LK_YL",
            {
                "BAT": {"val": 90},
                "EVTOP": {"type": 0x7E, "val": 0x12012303},
                "ALM": {"val": 0b10001},
                "HISLK": {"type": 1, "val": 0x1001},
            },
            device_id="LOCK1",
        ),
        make_device("SL_P", {"P1": {"val": 0x8A07000A}}, device_id="CTRL1"),
        make_device(
            "SL_OE_DE", {"P2": {"v": 1.5}, "P3": {"v": 200}}, device_id="PLUG1"
        ),
        make_device("SL_NATURE", {"P4": {"val": 215}}, device_id="NAT1"),
        make_device("SL_SC_WA", {"V": {"v": 88}}, device_id="WATER1"),
        make_device(
            "SL_SC_CA",
            {
                "P1": {"val": 215},
                "P2": {"val": 450},
                "P3": {"val": 500},
                "P4": {"v": 95},
            },
            device_id="CO21",
        ),
        make_device(
            "SL_SC_THL",
            {"T": {"val": 215}, "H": {"v": 55}, "Z": {"val": 100}, "V": {"v": 80}},
            device_id="ENV1",
        ),
        make_device("SL_SC_BG", {"V": {"val": 3000, "v": 79}}, device_id="GUARD1"),
        make_device(
            "SL_SC_BM", {"M": {"val": 1}, "V": {"val": 3000, "v": 82}}, device_id="BM1"
        ),
        make_device(
            "SL_SC_CQ",
            {"P1": {"val": 215}, "P4": {"val": 1200}, "P6": {"v": 3.2}},
            device_id="TVOC1",
        ),
        make_device("SL_DF_SR", {"T": {"val": 230}, "V": {"v": 81}}, device_id="DEF1"),
        make_device("ELIQ_EM", {"EPA": {"val": 125}}, device_id="METER1"),
        make_device("V_DLT_645_P", {"EE": {"v": 12}, "EP": {"v": 2}}, device_id="DLT1"),
        make_device(
            "V_485_P",
            {
                "EV": {"v": 230},
                "PM1": {"val": 50},
                "TVOC": {"v": 0.7},
                "T": {"val": 215},
            },
            device_id="MOD1",
        ),
        make_device(
            "OD_MFRESH_M8088",
            {"RM": {"val": 2}, "T": {"val": 215}, "PM": {"val": 22}},
            device_id="AIR1",
        ),
        make_device(
            "SL_SC_CN",
            {"P1": {"val": 50}, "P2": {"val": 20}, "P4": {"val": 30}},
            device_id="NOISE1",
        ),
        make_device("SL_SC_CM", {"P3": {"v": 87}}, device_id="CM1"),
        make_device("SL_P_A", {"P2": {"v": 92}}, device_id="SMOKE1"),
    ]
    hass = FakeHass("entry-1", devices, client=object())
    added = []

    asyncio.run(
        sensor_module.async_setup_entry(
            hass, FakeConfigEntry(), lambda entities: added.extend(entities)
        )
    )

    assert len(added) >= 24
    assert any(entity.entity_id == "sensor.sl_sc_ch_hub1_dev1_p1" for entity in added)
    assert any(entity.entity_id == "sensor.sl_lk_yl_hub1_lock1_bat" for entity in added)
    assert any(
        entity.entity_id == "sensor.sl_lk_yl_hub1_lock1_evtop" for entity in added
    )
    assert any(
        entity.entity_id == "sensor.sl_lk_yl_hub1_lock1_alm_desc" for entity in added
    )
    assert any(
        entity.entity_id == "sensor.sl_lk_yl_hub1_lock1_hislk" for entity in added
    )
    assert any(entity.entity_id == "sensor.sl_p_hub1_ctrl1_p1" for entity in added)
    assert any(entity.entity_id == "sensor.sl_sc_bg_hub1_guard1_v" for entity in added)
    assert any(entity.entity_id == "sensor.sl_sc_bm_hub1_bm1_v" for entity in added)
    assert any(entity.entity_id == "sensor.v_485_p_hub1_mod1_ev" for entity in added)


def test_sensor_entity_branches_and_properties():
    gas, _ = make_sensor_entity("SL_SC_CH", "P1", {"val": 11, "type": 1})
    smart_plug, _ = make_sensor_entity("SL_OE_DE", "P2", {"v": 1.5})
    co2, _ = make_sensor_entity("SL_SC_CA", "P3", {"val": 500})
    env, _ = make_sensor_entity("SL_SC_THL", "T", {"val": 215})
    cube_guard_battery, _ = make_sensor_entity("SL_SC_BG", "V", {"val": 3000, "v": 79})
    cube_motion_battery, _ = make_sensor_entity("SL_SC_BM", "V", {"val": 3000, "v": 82})
    controller_config, _ = make_sensor_entity("SL_P", "P1", {"val": 0x8A07000A})
    lock_battery, _ = make_sensor_entity("SL_LK_YL", "BAT", {"val": 90})
    lock_operation, _ = make_sensor_entity(
        "SL_LK_YL", "EVTOP", {"type": 0x7E, "val": 0x12012303}
    )
    lock_alarm, _ = make_sensor_entity("SL_LK_YL", "ALM_DESC", {"val": 0b10001})
    lock_history, _ = make_sensor_entity(
        "SL_LK_YL", "HISLK", {"type": 1, "val": 0x1001}
    )
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
    assert cube_guard_battery.device_class == sensor_module.SensorDeviceClass.BATTERY
    assert cube_guard_battery.state == 79
    assert cube_guard_battery.extra_state_attributes == {"raw": 3000}
    assert cube_motion_battery.device_class == sensor_module.SensorDeviceClass.BATTERY
    assert cube_motion_battery.state == 82
    assert cube_motion_battery.extra_state_attributes == {"raw": 3000}
    assert lock_battery.device_name == "Battery"
    assert lock_battery.name == "Battery"
    assert lock_battery.device_class == sensor_module.SensorDeviceClass.BATTERY
    assert lock_battery.state == 90
    assert lock_operation.device_name == "Last Operation"
    assert lock_operation.state == "Operation type 18 by user id 291"
    assert lock_operation.unit_of_measurement is None
    assert lock_operation.extra_state_attributes == {
        "record_type": 0x12,
        "user_id_raw": 0x0123,
        "user_flag": 0x03,
        "user_role": "administrator",
        "raw": 0x12012303,
    }
    assert lock_alarm.entity_id == "sensor.sl_lk_yl_hub1_dev1_alm_desc"
    assert lock_alarm.device_name == "Alarm Description"
    assert lock_alarm.state == "Error alarm, Low battery alarm"
    assert lock_alarm.device_class == sensor_module.SensorDeviceClass.ENUM
    assert lock_alarm.extra_state_attributes == {
        "error_alarm": True,
        "duress_alarm": False,
        "lock_pick_alarm": False,
        "mechanical_key_alarm": False,
        "low_battery_alarm": True,
        "exception_alarm": False,
        "doorbell": False,
        "fire_alarm": False,
        "intrusion_alarm": False,
        "factory_reset_alarm": False,
        "raw": 17,
    }
    assert lock_history.device_name == "Last Unlock"
    assert lock_history.name == "Last Unlock"
    assert lock_history.state == "Unlock with Password by user 1"
    assert lock_history.device_class is None
    assert lock_history.unit_of_measurement is None
    assert lock_history.extra_state_attributes == {
        "unlocking_method": "Password",
        "unlocking_user": 1,
        "raw": 0x1001,
    }
    assert controller_config.state == 0x8A07000A
    assert controller_config.extra_state_attributes["working_mode"] == (
        "three_way_switch_rocker"
    )
    assert controller_config.extra_state_attributes["auto_close_delay"] == 10
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
    assert (
        sensor_module._display_value(
            {"type": 0x7E, "val": 0x12012303}, "SL_LK_YL", "EVTOP"
        )
        == "Operation type 18 by user id 291"
    )
    assert (
        sensor_module._display_value({"val": 0b10001}, "SL_LK_YL", "ALM_DESC")
        == "Error alarm, Low battery alarm"
    )
    assert sensor_module._display_value({"val": 0}, "SL_LK_YL", "ALM_DESC") == "Normal"
    assert (
        sensor_module._display_value({"val": 0x1001}, "SL_LK_YL", "HISLK")
        == "Unlock with Password by user 1"
    )
    assert sensor_module._display_value({"val": 0x8A07000A}, "SL_P", "P1") == 0x8A07000A
    assert sensor_module._display_value({"val": 215}) == 21.5
    assert sensor_module._display_float_value({"val": ieee}) == 12.5
    assert sensor_module._float32_from_int(ieee) == 12.5
    assert sensor_module._is_modbus_sensor_key("EE1") is True
    assert sensor_module._is_modbus_sensor_key("PM10") is True
    assert (
        sensor_module._modbus_sensor_metadata("EPF1")[0]
        == sensor_module.SensorDeviceClass.POWER_FACTOR
    )
    assert sensor_module._modbus_sensor_metadata("O2VOL")[1] == sensor_module.PERCENTAGE
    assert sensor_module._modbus_sensor_metadata("UNKNOWN") == (None, "None")
    assert sensor_module._state_attributes(
        {"type": 1, "val": 11}, "SL_SC_CH", "P1"
    ) == {"alarm": True, "raw": 11}
    assert sensor_module._state_attributes(
        {"type": 1, "val": 50}, "SL_SC_CN", "P1"
    ) == {"alarm": True, "raw": 50}
    assert sensor_module._state_attributes(
        {"val": 0b10001}, "SL_LK_YL", "ALM_DESC"
    ) == {
        "error_alarm": True,
        "duress_alarm": False,
        "lock_pick_alarm": False,
        "mechanical_key_alarm": False,
        "low_battery_alarm": True,
        "exception_alarm": False,
        "doorbell": False,
        "fire_alarm": False,
        "intrusion_alarm": False,
        "factory_reset_alarm": False,
        "raw": 17,
    }
    assert sensor_module._state_attributes({"val": 0x800B}, "SL_LK_YL", "HISLK") == {
        "unlocking_method": "Bluetooth unlocking",
        "unlocking_user": 11,
        "raw": 0x800B,
    }
    assert sensor_module._doorlock_operation_user_role(0) == "deleted_user"
    assert sensor_module._doorlock_operation_user_role(1) == "common_user"
    assert sensor_module._doorlock_operation_user_role(2) == "unknown"
    assert (
        sensor_module._doorlock_operation_summary({"type": 0x4E, "val": 0x12}) is None
    )
    assert (
        sensor_module._doorlock_operation_summary({"type": 0x6E, "val": 0x120123})
        == "Operation type 18 by user id 291"
    )
    real_evtop_sample = {"type": 0x6E, "val": 0x061002, "valts": 1776904708389}
    assert (
        sensor_module._display_value(real_evtop_sample, "SL_LK_LS", "EVTOP")
        == "Operation type 6 by user id 4098"
    )
    assert sensor_module._state_attributes(real_evtop_sample, "SL_LK_LS", "EVTOP") == {
        "record_type": 6,
        "user_id_raw": 4098,
        "raw": 397314,
    }
    assert sensor_module._doorlock_operation_value_length({"type": 0x4E}) == 8
    assert sensor_module._doorlock_operation_value_length({"type": 0x6E}) == 24
    assert sensor_module._doorlock_operation_value_length({"type": 0x7E}) == 32
    assert sensor_module._generic_controller_config_attributes({"val": 0x02010005}) == {
        "software_configured": False,
        "working_mode": "two_wire_curtain",
        "working_mode_raw": 2,
        "inching": False,
        "ctrl1_enabled": True,
        "ctrl2_enabled": False,
        "ctrl3_enabled": False,
        "auto_close_delay": 5,
        "auto_close_config": 0x10005,
    }
