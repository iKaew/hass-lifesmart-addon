import asyncio
import importlib

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from tests.lifesmart_entity_helpers import make_binary_sensor

binary_sensor_module = importlib.import_module("custom_components.lifesmart.binary_sensor")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(self, entry_id, devices, exclude_devices=None, exclude_hubs=None, client=None):
        self.data = {
            binary_sensor_module.DOMAIN: {
                entry_id: {
                    "devices": devices,
                    "exclude_devices": exclude_devices or [],
                    "exclude_hubs": exclude_hubs or [],
                    "client": client,
                }
            }
        }


class FakeDevice:
    def __init__(self, name="Device", agt="HUB1", me="LOCK1", devtype="SL_ND_A", ver="1.0"):
        self._name = name
        self._agt = agt
        self._me = me
        self._devtype = devtype
        self._attributes = {"agt": agt, "me": me, "devtype": devtype}


def make_setup_device(device_type, data, device_id="DEVICE1", hub_id="HUB1"):
    return {
        "name": "Setup Device",
        "devtype": device_type,
        "agt": hub_id,
        "me": device_id,
        "ver": "1.0",
        "data": data,
    }


def test_async_setup_entry_creates_supported_binary_sensors_and_skips_excluded():
    devices = [
        make_setup_device("SL_SC_G", {"G": {"val": 0}, "ignored": {"val": 0}}),
        make_setup_device("SL_DF_SR", {"SR": {"type": 1}, "TR": {"type": 0}}, device_id="DEF1"),
        make_setup_device("SL_SC_WA", {"WA": {"val": 1}, "V": {"v": 87}}, device_id="LEAK1"),
        make_setup_device("SL_SC_BM", {"M": {"val": 1}, "V": {"v": 82}}, device_id="BM1"),
        make_setup_device("SL_P_IR_V2", {"P2": {"type": 1, "val": 0}}, device_id="IR1"),
        make_setup_device("SL_SC_CN", {"P3": {"type": 1, "val": 1}}, device_id="NOISE1"),
        make_setup_device(
            "SL_LK_YL",
            {
                "EVTLO": {"type": 1, "val": 0x1001},
                "ALM": {"val": 0b10001},
            },
            device_id="LOCK1",
        ),
        make_setup_device("SL_SPOT", {"P1": {"val": 1}}, device_id="SKIPME"),
        make_setup_device("SL_SC_G", {"G": {"val": 0}}, device_id="EXCLUDED_DEVICE"),
        make_setup_device("SL_SC_G", {"G": {"val": 0}}, device_id="EXCLUDED_HUB", hub_id="HUBX"),
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
        binary_sensor_module.async_setup_entry(
            hass, config_entry, lambda entities: added_entities.extend(entities)
        )
    )

    entity_ids = {entity.entity_id for entity in added_entities}

    assert len(added_entities) == 9
    assert "binary_sensor.sl_sc_g_hub1_device1_g" in entity_ids
    assert "binary_sensor.sl_df_sr_hub1_def1_sr" in entity_ids
    assert "binary_sensor.sl_df_sr_hub1_def1_tr" in entity_ids
    assert "binary_sensor.sl_sc_wa_hub1_leak1_wa" in entity_ids
    assert "binary_sensor.sl_sc_bm_hub1_bm1_m" in entity_ids
    assert "binary_sensor.sl_p_ir_v2_hub1_ir1_p2" in entity_ids
    assert "binary_sensor.sl_sc_cn_hub1_noise1_p3" in entity_ids
    assert "binary_sensor.sl_lk_yl_hub1_lock1_evtlo" in entity_ids
    assert "binary_sensor.sl_lk_yl_hub1_lock1_alm" in entity_ids


def test_guard_motion_water_and_smoke_binary_sensor_initialization():
    door = make_binary_sensor("SL_SC_G", "G", {"val": 0})
    vibration = make_binary_sensor("SL_SC_G", "AXS", {"val": 1})
    occupancy = make_binary_sensor("SL_SC_G", "B", {"val": 1})
    cube_door = make_binary_sensor("SL_SC_BG", "G", {"val": 0})
    cube_button = make_binary_sensor("SL_SC_BG", "B", {"val": 1})
    cube_vibration = make_binary_sensor("SL_SC_BG", "AXS", {"val": 1})
    ir_pairing = make_binary_sensor("SL_P_IR", "P2", {"type": 1, "val": 0})
    motion = make_binary_sensor("SL_SC_MHW", "M", {"val": 1})
    cube_motion = make_binary_sensor("SL_SC_BM", "M", {"val": 1})
    radar = make_binary_sensor("SL_P_RM", "P1", {"val": 1})
    leak = make_binary_sensor("SL_SC_WA", "WA", {"val": 1})
    smoke_fallback = make_binary_sensor("SL_P_A", "P2", {"val": 1})

    assert door.device_class == BinarySensorDeviceClass.DOOR
    assert door.is_on is True
    assert vibration.device_class == BinarySensorDeviceClass.VIBRATION
    assert vibration.is_on is True
    assert occupancy.device_class is None
    assert occupancy.is_on is True
    assert cube_door.device_class == BinarySensorDeviceClass.DOOR
    assert cube_door.is_on is True
    assert cube_button.device_class is None
    assert cube_button.is_on is True
    assert cube_vibration.device_class == BinarySensorDeviceClass.VIBRATION
    assert cube_vibration.is_on is True
    assert ir_pairing.device_class is None
    assert ir_pairing.is_on is True
    assert ir_pairing.extra_state_attributes == {"raw": 0}
    assert motion.device_class == BinarySensorDeviceClass.MOTION
    assert motion.is_on is True
    assert cube_motion.device_class == BinarySensorDeviceClass.MOTION
    assert cube_motion.is_on is True
    assert radar.device_class == BinarySensorDeviceClass.MOTION
    assert radar.is_on is True
    assert leak.device_class == BinarySensorDeviceClass.MOISTURE
    assert leak.is_on is True
    assert smoke_fallback.device_class == BinarySensorDeviceClass.SMOKE
    assert smoke_fallback.is_on is True


def test_lock_binary_sensor_variants_and_attributes():
    lock = make_binary_sensor("SL_LK_LS", "EVTLO", {"type": 1, "val": 0x200A})
    alarm = make_binary_sensor("SL_LK_LS", "ALM", {"val": 3})
    doorbell = make_binary_sensor("SL_LK_LS", "EVTBELL", {"type": 1, "val": 7})

    assert lock.name == "Status"
    assert lock.device_class == BinarySensorDeviceClass.LOCK
    assert lock.is_on is True
    assert lock.extra_state_attributes == {
        "unlocking_method": "Fingerprint",
        "unlocking_user": 10,
    }

    assert alarm.name == "Alarm"
    assert alarm.device_class == BinarySensorDeviceClass.PROBLEM
    assert alarm.is_on is True
    assert alarm.extra_state_attributes == {
        "raw": 3,
        "error_alarm": True,
        "duress_alarm": True,
        "lock_pick_alarm": False,
        "mechanical_key_alarm": False,
        "low_battery_alarm": False,
        "exception_alarm": False,
        "doorbell": False,
        "fire_alarm": False,
        "intrusion_alarm": False,
        "factory_reset_alarm": False,
    }

    assert doorbell.name == "Doorbell"
    assert doorbell.device_class == BinarySensorDeviceClass.SOUND
    assert doorbell.is_on is True
    assert doorbell.extra_state_attributes == {"raw": 7}


def test_binary_sensor_name_device_info_unique_id_and_attrs():
    sensor = make_binary_sensor(
        "SL_SC_G",
        "G",
        {"val": 0, "name": "Front Door"},
    )

    assert sensor.name == "Front Door"
    assert sensor.unique_id == sensor.entity_id
    assert sensor.extra_state_attributes == {}
    assert sensor.device_info["identifiers"] == {
        (binary_sensor_module.DOMAIN, "HUB1", "DEVICE1")
    }
    assert sensor.device_info["manufacturer"] == binary_sensor_module.MANUFACTURER
    assert sensor.device_info["model"] == "SL_SC_G"
    assert sensor.device_info["sw_version"] == "1.0"
    assert sensor.device_info["via_device"] == (binary_sensor_module.DOMAIN, "HUB1")


def test_update_state_handles_none_regular_updates_and_lock_events():
    sensor = make_binary_sensor("SL_SC_G", "G", {"val": 0})
    lock = make_binary_sensor("SL_LK_LS", "EVTLO", {"type": 0, "val": 0x1001})
    update_calls = []
    lock_calls = []
    sensor.schedule_update_ha_state = lambda: update_calls.append("guard")
    lock.schedule_update_ha_state = lambda: lock_calls.append("lock")

    asyncio.run(sensor._update_state(None))
    asyncio.run(sensor._update_state({"devtype": "SL_SC_G", "idx": "G", "val": 1}))
    asyncio.run(lock._update_state({"devtype": "SL_LK_LS", "idx": "EVTLO", "type": 1, "val": 0x7005}))

    assert sensor.is_on is False
    assert update_calls == ["guard"]
    assert lock.is_on is True
    assert lock.extra_state_attributes == {
        "unlocking_method": "APP",
        "unlocking_user": 5,
    }
    assert lock_calls == ["lock"]


def test_state_from_data_covers_special_cases():
    guard = make_binary_sensor("SL_SC_G", "G", {"val": 0})
    controller = make_binary_sensor("SL_JEMA", "P6", {"type": 1, "val": 0})
    defed = make_binary_sensor("SL_DF_SR", "TR", {"type": 0})
    gas = make_binary_sensor("SL_SC_CH", "P3", {"type": 0, "val": 0})
    doorbell = make_binary_sensor("SL_LK_LS", "EVTBELL", {"type": 0, "val": 0})
    generic = make_binary_sensor("SL_SC_G", "B", {"val": 0})

    assert guard._state_from_data({"devtype": "SL_SC_G", "idx": "G", "val": 0}) is True
    assert controller._state_from_data({"devtype": "SL_JEMA", "idx": "P6", "type": 1, "val": 0}) is True
    assert controller._state_from_data({"devtype": "SL_P_IR", "idx": "P2", "type": 1, "val": 0}) is True
    assert defed._state_from_data({"devtype": "SL_DF_SR", "idx": "TR", "type": 1}) is True
    assert gas._state_from_data({"devtype": "SL_SC_CH", "idx": "P3", "type": 1}) is True
    assert doorbell._state_from_data({"devtype": "SL_LK_LS", "idx": "EVTBELL", "type": 1}) is True
    assert generic._state_from_data({"devtype": "SL_SC_G", "idx": "B", "val": 2}) is True


def test_async_added_to_hass_registers_dispatcher_callback(monkeypatch):
    sensor = make_binary_sensor("SL_SC_G", "G", {"val": 0})
    sensor.hass = object()
    removers = []
    dispatcher_calls = []

    def fake_async_dispatcher_connect(hass, signal, callback):
        dispatcher_calls.append((hass, signal, callback))
        return "remove-token"

    sensor.async_on_remove = lambda remover: removers.append(remover)
    monkeypatch.setattr(
        binary_sensor_module, "async_dispatcher_connect", fake_async_dispatcher_connect
    )

    asyncio.run(sensor.async_added_to_hass())

    assert dispatcher_calls[0][0] is sensor.hass
    assert dispatcher_calls[0][1] == f"{binary_sensor_module.LIFESMART_SIGNAL_UPDATE_ENTITY}_{sensor.entity_id}"
    assert dispatcher_calls[0][2] == sensor._update_state
    assert removers == ["remove-token"]


def test_doorlock_helper_functions_cover_known_and_unknown_methods():
    assert binary_sensor_module.extract_doorlock_unlocking_method({"val": 0x1001}) == "Password"
    assert binary_sensor_module.extract_doorlock_unlocking_method({"val": 0x5001}) == "Remote unlocking"
    assert binary_sensor_module.extract_doorlock_unlocking_method({"val": 0xF001}) == "Error"
    assert binary_sensor_module.extract_doorlock_unlocking_method({"val": 0x0001}) == "Undefined"
    assert binary_sensor_module.is_doorlock_unlocked({"type": 1}) is True
    assert binary_sensor_module.get_doorlock_unlocking_user({"val": 0x700A}) == 10
    assert binary_sensor_module.build_doorlock_attribute({"val": 0x800B}) == {
        "unlocking_method": "Bluetooth unlocking",
        "unlocking_user": 11,
    }
