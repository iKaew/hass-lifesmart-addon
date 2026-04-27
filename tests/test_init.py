import asyncio
import importlib
import json

import pytest

lifesmart_init = importlib.import_module("custom_components.lifesmart")
from custom_components.lifesmart.const import (
    CONF_AI_INCLUDE_AGTS,
    CONF_AI_INCLUDE_ITEMS,
    CONF_EXCLUDE_AGTS,
    CONF_EXCLUDE_ITEMS,
    CONF_LIFESMART_APPKEY,
    CONF_LIFESMART_APPTOKEN,
    CONF_LIFESMART_USERID,
    CONF_LIFESMART_USERPASSWORD,
    DEVICE_ID_KEY,
    DOMAIN,
    HUB_ID_KEY,
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    LIFESMART_STATE_MANAGER,
    NATURE_CLIMATE_KEY,
    SUBDEVICE_INDEX_KEY,
    UPDATE_LISTENER,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_MAX_COLOR_TEMP_KELVIN,
    ATTR_MIN_COLOR_TEMP_KELVIN,
)
from homeassistant.const import CONF_REGION
from homeassistant.const import STATE_OFF, STATE_ON


class FakeConfigEntry:
    def __init__(self, data, options=None, entry_id="entry-1"):
        self.data = data
        self.options = options or {}
        self.entry_id = entry_id
        self.update_listener = None

    def add_update_listener(self, listener):
        self.update_listener = listener
        return "listener-token"


class FakeConfigEntriesManager:
    def __init__(self):
        self.forward_calls = []
        self.reload_calls = []
        self.unload_calls = []

    async def async_forward_entry_setups(self, config_entry, platforms):
        self.forward_calls.append((config_entry, tuple(platforms)))

    async def async_reload(self, entry_id):
        self.reload_calls.append(entry_id)

    async def async_unload_platforms(self, entry, platforms):
        self.unload_calls.append((entry, tuple(platforms)))
        return True


class FakeServices:
    def __init__(self):
        self.registrations = []

    def async_register(self, domain, service, handler, schema=None):
        self.registrations.append((domain, service, handler, schema))


class FakeStates:
    def __init__(self):
        self._states = {}

    def get(self, entity_id):
        return self._states.get(entity_id)

    def set(self, entity_id, state, attrs):
        self._states[entity_id] = FakeState(state, attrs)


class FakeState:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class FakeHass:
    def __init__(self):
        self.data = {}
        self.config_entries = FakeConfigEntriesManager()
        self.services = FakeServices()
        self.states = FakeStates()


class FakeDeviceRegistry:
    def __init__(self):
        self.created = []

    def async_get_or_create(self, **kwargs):
        self.created.append(kwargs)


class FakeWebSocketApp:
    instances = []

    def __init__(self, url, on_open, on_message, on_error, on_close):
        self.url = url
        self.on_open = on_open
        self.on_message = on_message
        self.on_error = on_error
        self.on_close = on_close
        self.sent = []
        FakeWebSocketApp.instances.append(self)

    def send(self, payload):
        self.sent.append(payload)


class FakeStatesManager:
    instances = []

    def __init__(self, ws):
        self.ws = ws
        self.started = False
        FakeStatesManager.instances.append(self)

    def start_keep_alive(self):
        self.started = True


class FakeLifeSmartClient:
    instances = []
    login_response = {"code": "success"}
    devices_response = []

    def __init__(self, region, appkey, apptoken, userid, userpassword):
        self.region = region
        self.appkey = appkey
        self.apptoken = apptoken
        self.userid = userid
        self.userpassword = userpassword
        self.login_calls = 0
        self.device_calls = 0
        FakeLifeSmartClient.instances.append(self)

    async def login_async(self):
        self.login_calls += 1
        return self.login_response

    async def get_all_device_async(self):
        self.device_calls += 1
        return self.devices_response

    def get_wss_url(self):
        return "wss://example.invalid/wsapp/"

    def generate_wss_auth(self):
        return '{"id": 1, "method": "WbAuth"}'


def make_config_entry(options=None):
    return FakeConfigEntry(
        data={
            CONF_LIFESMART_APPKEY: "data-appkey",
            CONF_LIFESMART_APPTOKEN: "data-apptoken",
            CONF_LIFESMART_USERID: "data-user",
            CONF_LIFESMART_USERPASSWORD: "data-password",
            CONF_REGION: "data-region",
        },
        options=options,
    )


def patch_setup_dependencies(monkeypatch, device_registry):
    FakeLifeSmartClient.instances.clear()
    FakeWebSocketApp.instances.clear()
    FakeStatesManager.instances.clear()
    monkeypatch.setattr(lifesmart_init, "LifeSmartClient", FakeLifeSmartClient)
    monkeypatch.setattr(lifesmart_init.device_registry, "async_get", lambda hass: device_registry)
    monkeypatch.setattr(lifesmart_init.websocket, "WebSocketApp", FakeWebSocketApp)
    monkeypatch.setattr(lifesmart_init, "LifeSmartStatesManager", FakeStatesManager)


def setup_entry_for_ws_tests(monkeypatch, devices, options=None):
    hass = FakeHass()
    config_entry = make_config_entry(options=options)
    device_reg = FakeDeviceRegistry()
    dispatch_calls = []

    FakeLifeSmartClient.login_response = {"code": "success"}
    FakeLifeSmartClient.devices_response = devices
    patch_setup_dependencies(monkeypatch, device_reg)
    monkeypatch.setattr(
        lifesmart_init,
        "dispatcher_send",
        lambda hass_obj, signal, data: dispatch_calls.append((signal, data)),
    )

    result = asyncio.run(lifesmart_init.async_setup_entry(hass, config_entry))

    assert result is True
    return hass, config_entry, FakeWebSocketApp.instances[0], dispatch_calls


def send_ws_device_update(ws, payload):
    ws.on_message(ws, json.dumps({"type": "io", "msg": payload}))


def test_async_setup_entry_initializes_client_services_and_websocket(monkeypatch):
    hass = FakeHass()
    config_entry = make_config_entry(
        options={
            CONF_LIFESMART_APPKEY: "opt-appkey",
            CONF_EXCLUDE_ITEMS: None,
            CONF_EXCLUDE_AGTS: None,
            CONF_AI_INCLUDE_AGTS: None,
            CONF_AI_INCLUDE_ITEMS: None,
            CONF_REGION: "opt-region",
        }
    )
    device_reg = FakeDeviceRegistry()
    FakeLifeSmartClient.login_response = {"code": "success"}
    FakeLifeSmartClient.devices_response = [
        {HUB_ID_KEY: "HUB1"},
        {HUB_ID_KEY: "HUB2"},
        {HUB_ID_KEY: "HUB1"},
    ]
    patch_setup_dependencies(monkeypatch, device_reg)

    result = asyncio.run(lifesmart_init.async_setup_entry(hass, config_entry))

    assert result is True
    client = FakeLifeSmartClient.instances[0]
    assert (client.region, client.appkey, client.apptoken, client.userid, client.userpassword) == (
        "opt-region",
        "opt-appkey",
        "data-apptoken",
        "data-user",
        "data-password",
    )
    assert client.login_calls == 1
    assert client.device_calls == 1
    assert hass.data[DOMAIN][config_entry.entry_id]["client"] is client
    assert hass.data[DOMAIN][config_entry.entry_id]["devices"] == FakeLifeSmartClient.devices_response
    assert hass.data[DOMAIN][config_entry.entry_id]["exclude_devices"] == []
    assert hass.data[DOMAIN][config_entry.entry_id]["exclude_hubs"] == []
    assert hass.data[DOMAIN][config_entry.entry_id]["ai_include_hubs"] == []
    assert hass.data[DOMAIN][config_entry.entry_id]["ai_include_items"] == []
    assert hass.data[DOMAIN][config_entry.entry_id][UPDATE_LISTENER] == "listener-token"
    assert config_entry.update_listener is lifesmart_init._async_update_listener
    assert len(device_reg.created) == 2
    assert {entry["name"] for entry in device_reg.created} == {
        "LifeSmart Hub HUB1",
        "LifeSmart Hub HUB2",
    }
    assert [name for _, name, _, _ in hass.services.registrations] == [
        "send_ir_code",
        "send_keys",
        "send_ackeys",
        "scene_set",
    ]
    assert hass.config_entries.forward_calls == [
        (config_entry, tuple(lifesmart_init.SUPPORTED_PLATFORMS))
    ]
    assert isinstance(hass.data[DOMAIN][LIFESMART_STATE_MANAGER], FakeStatesManager)
    assert hass.data[DOMAIN][LIFESMART_STATE_MANAGER].started is True
    ws = FakeWebSocketApp.instances[0]
    assert ws.url == "wss://example.invalid/wsapp/"
    ws.on_open(ws)
    assert ws.sent == ['{"id": 1, "method": "WbAuth"}']


def test_async_setup_entry_raises_when_login_fails(monkeypatch):
    hass = FakeHass()
    config_entry = make_config_entry()
    device_reg = FakeDeviceRegistry()
    FakeLifeSmartClient.login_response = {"code": "failure", "message": "bad auth"}
    FakeLifeSmartClient.devices_response = []
    patch_setup_dependencies(monkeypatch, device_reg)

    with pytest.raises(Exception, match="Error connecting to LifeSmart API"):
        asyncio.run(lifesmart_init.async_setup_entry(hass, config_entry))

    client = FakeLifeSmartClient.instances[0]
    assert client.login_calls == 1
    assert client.device_calls == 0
    assert hass.data.get(DOMAIN, {}) == {}
    assert hass.services.registrations == []


def test_async_setup_entry_raises_when_device_fetch_returns_error(monkeypatch):
    hass = FakeHass()
    config_entry = make_config_entry()
    device_reg = FakeDeviceRegistry()
    FakeLifeSmartClient.login_response = {"code": "success"}
    FakeLifeSmartClient.devices_response = {"code": 500, "message": "device fetch failed"}
    patch_setup_dependencies(monkeypatch, device_reg)

    with pytest.raises(Exception, match="Error connecting to LifeSmart API"):
        asyncio.run(lifesmart_init.async_setup_entry(hass, config_entry))

    client = FakeLifeSmartClient.instances[0]
    assert client.login_calls == 1
    assert client.device_calls == 1
    assert hass.data.get(DOMAIN, {}) == {}
    assert device_reg.created == []


def test_async_update_listener_reloads_entry():
    hass = FakeHass()
    config_entry = FakeConfigEntry(data={}, entry_id="entry-42")

    asyncio.run(lifesmart_init._async_update_listener(hass, config_entry))

    assert hass.config_entries.reload_calls == ["entry-42"]


def test_async_unload_entry_forwards_to_platform_unload():
    hass = FakeHass()
    config_entry = FakeConfigEntry(data={}, entry_id="entry-99")

    result = asyncio.run(lifesmart_init.async_unload_entry(hass, config_entry))

    assert result is True
    assert hass.config_entries.unload_calls == [
        (config_entry, tuple(lifesmart_init.SUPPORTED_PLATFORMS))
    ]


def test_on_message_dispatches_switch_updates(monkeypatch):
    device_type = next(iter(lifesmart_init.SUPPORTED_SWTICH_TYPES))
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "DEV1",
                "devtype": device_type,
            }
        ],
    )

    ws.on_message(
        ws,
        json.dumps(
            {
                "type": "io",
                "msg": {
                    "devtype": device_type,
                    HUB_ID_KEY: "HUB1",
                    DEVICE_ID_KEY: "DEV1",
                    SUBDEVICE_INDEX_KEY: next(iter(lifesmart_init.SUPPORTED_SUB_SWITCH_TYPES)),
                    "type": 1,
                    "val": 1,
                },
            }
        ),
    )

    expected_entity_id = lifesmart_init.generate_entity_id(
        device_type,
        "HUB1",
        "DEV1",
        next(iter(lifesmart_init.SUPPORTED_SUB_SWITCH_TYPES)),
    )
    assert dispatch_calls == [
        (
            f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{expected_entity_id}",
            {
                "devtype": device_type,
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "DEV1",
                SUBDEVICE_INDEX_KEY: next(iter(lifesmart_init.SUPPORTED_SUB_SWITCH_TYPES)),
                "type": 1,
                "val": 1,
            },
        )
    ]
    assert hass.states._states == {}


def test_on_message_updates_cover_and_light_and_sensor_states(monkeypatch):
    cover_type = next(iter(lifesmart_init.COVER_TYPES))
    light_type = next(iter(lifesmart_init.LIGHT_DIMMER_TYPES))
    smart_plug_type = next(iter(lifesmart_init.SMART_PLUG_TYPES))
    water_type = next(iter(lifesmart_init.WATER_LEAK_SENSOR_TYPES))
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "COVER1", "devtype": cover_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "LIGHT1", "devtype": light_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "PLUG1", "devtype": smart_plug_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "WATER1", "devtype": water_type},
        ],
    )

    cover_entity = lifesmart_init.generate_entity_id(cover_type, "HUB1", "COVER1", "P1")
    light_entity = lifesmart_init.generate_entity_id(light_type, "HUB1", "LIGHT1", "P1")
    plug_entity = lifesmart_init.generate_entity_id(smart_plug_type, "HUB1", "PLUG1", "P2")
    water_entity = lifesmart_init.generate_entity_id(water_type, "HUB1", "WATER1", "V")

    hass.states.set(cover_entity, "closed", {"current_position": 0})
    hass.states.set(
        light_entity,
        STATE_OFF,
        {
            ATTR_BRIGHTNESS: 0,
            ATTR_MIN_COLOR_TEMP_KELVIN: 2700,
            ATTR_MAX_COLOR_TEMP_KELVIN: 6500,
            ATTR_COLOR_TEMP_KELVIN: 2700,
        },
    )
    hass.states.set(plug_entity, 0, {"unit": "W"})
    hass.states.set(water_entity, 0, {"unit": "%"})

    for payload in [
        {
            "devtype": cover_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "COVER1",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 2,
            "val": 64,
        },
        {
            "devtype": light_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "LIGHT1",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 1,
            "val": 123,
        },
            {
                "devtype": smart_plug_type,
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "PLUG1",
                SUBDEVICE_INDEX_KEY: "P2",
                "type": 1,
                "v": 17,
            },
        {
            "devtype": water_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "WATER1",
            SUBDEVICE_INDEX_KEY: "V",
            "type": 1,
            "v": 88,
        },
    ]:
        ws.on_message(ws, json.dumps({"type": "io", "msg": payload}))

    assert dispatch_calls == []
    assert hass.states.get(cover_entity).state == "open"
    assert hass.states.get(cover_entity).attributes["current_position"] == 64
    assert hass.states.get(light_entity).state == STATE_ON
    assert hass.states.get(light_entity).attributes[ATTR_BRIGHTNESS] == 123
    assert hass.states.get(plug_entity).state == 17
    assert hass.states.get(water_entity).state == 88


def test_on_message_routes_nature_thermostat_and_ignores_non_io(monkeypatch):
    nature_type = next(iter(lifesmart_init.NATURE_TYPES))
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "NATURE1",
                "devtype": nature_type,
            }
        ],
        options={
            CONF_AI_INCLUDE_ITEMS: ["AI1"],
            CONF_AI_INCLUDE_AGTS: ["HUB1"],
        },
    )
    monkeypatch.setattr(lifesmart_init, "is_nature_thermostat", lambda raw_device: True)

    ws.on_message(ws, json.dumps({"msg": {"ignored": True}}))
    ws.on_message(ws, json.dumps({"type": "status", "msg": {"ignored": True}}))
    ws.on_message(
        ws,
        json.dumps(
            {
                "type": "io",
                "msg": {
                    "devtype": nature_type,
                    HUB_ID_KEY: "HUB1",
                    DEVICE_ID_KEY: "NATURE1",
                    SUBDEVICE_INDEX_KEY: "P1",
                    "type": 1,
                    "val": 20,
                },
            }
        ),
    )
    ws.on_message(
        ws,
        json.dumps(
            {
                "type": "io",
                "msg": {
                    "devtype": "SL_SPOT",
                    HUB_ID_KEY: "HUB1",
                    DEVICE_ID_KEY: "AI1",
                    SUBDEVICE_INDEX_KEY: "s",
                    "stat": 3,
                },
            }
        ),
    )

    climate_entity_id = lifesmart_init.generate_entity_id(
        nature_type, "HUB1", "NATURE1", NATURE_CLIMATE_KEY
    )
    assert dispatch_calls == [
        (
            f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{climate_entity_id}",
            {
                "devtype": nature_type,
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "NATURE1",
                SUBDEVICE_INDEX_KEY: "P1",
                "type": 1,
                "val": 20,
            },
        )
    ]


@pytest.mark.parametrize(
    ("device_type", "sub_device_key"),
    [
        ("OD_MFRESH_M8088", "O"),
        ("SL_P", "P2"),
        ("SL_JEMA", "P8"),
        ("V_485_P", "L2"),
        ("SL_P", "P6"),
        ("SL_SC_G", "G"),
        ("SL_SC_WA", "WA"),
        ("SL_P_RM", "P1"),
        ("SL_DF_GG", "GA"),
        ("SL_DF_GG", "T"),
        ("SL_SC_CA", "P1"),
        ("SL_SC_THL", "T"),
        ("SL_SC_CQ", "P6"),
        ("SL_SC_CM", "P3"),
        ("SL_P_A", "P2"),
        ("SL_SC_CN", "P3"),
        ("SL_SC_CH", "P2"),
        ("SL_ALM", "P1"),
        ("ELIQ_EM", "EPA"),
        ("V_DLT_645_P", "EE"),
        ("V_485_P", "CO2PPM"),
        ("V_485_P", "EPF2"),
        ("V_485_P", "PM10"),
        ("OD_MFRESH_M8088", "PM"),
        ("SL_SC_BE", "P9"),
        ("SL_SPOT", "P1"),
        ("V_AIR_P", "O"),
        ("SL_LK_LS", "BAT"),
        ("SL_LK_LS", "EVTLO"),
        ("SL_LK_YL", "EVTOP"),
        ("SL_LK_YL", "HISLK"),
    ],
)
def test_on_message_dispatches_supported_device_update_families(
    monkeypatch, device_type, sub_device_key
):
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "DEV1",
                "devtype": device_type,
            }
        ],
    )
    payload = {
        "devtype": device_type,
        HUB_ID_KEY: "HUB1",
        DEVICE_ID_KEY: "DEV1",
        SUBDEVICE_INDEX_KEY: sub_device_key,
        "type": 1,
        "val": 1,
        "v": 1,
    }

    send_ws_device_update(ws, payload)

    expected_entity_id = lifesmart_init.generate_entity_id(
        device_type, "HUB1", "DEV1", sub_device_key
    )
    assert dispatch_calls == [
        (f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{expected_entity_id}", payload)
    ]
    assert hass.states._states == {}


def test_on_message_routes_nature_sensor_update_when_not_thermostat(monkeypatch):
    nature_type = next(iter(lifesmart_init.NATURE_TYPES))
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "NATURE1",
                "devtype": nature_type,
            }
        ],
    )
    monkeypatch.setattr(lifesmart_init, "is_nature_thermostat", lambda raw_device: False)
    payload = {
        "devtype": nature_type,
        HUB_ID_KEY: "HUB1",
        DEVICE_ID_KEY: "NATURE1",
        SUBDEVICE_INDEX_KEY: "P4",
        "type": 1,
        "val": 23,
    }

    send_ws_device_update(ws, payload)

    expected_entity_id = lifesmart_init.generate_entity_id(
        nature_type, "HUB1", "NATURE1", "P4"
    )
    assert dispatch_calls == [
        (f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{expected_entity_id}", payload)
    ]


def test_on_message_ignores_excluded_and_unsupported_updates(monkeypatch):
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "EXCLUDED_DEV", "devtype": "SL_OL"},
            {HUB_ID_KEY: "EXCLUDED_HUB", DEVICE_ID_KEY: "DEV1", "devtype": "SL_OL"},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "UNSUPPORTED", "devtype": "UNKNOWN"},
        ],
        options={
            CONF_EXCLUDE_ITEMS: ["EXCLUDED_DEV"],
            CONF_EXCLUDE_AGTS: ["EXCLUDED_HUB"],
        },
    )

    for payload in [
        {
            "devtype": "SL_OL",
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "EXCLUDED_DEV",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 1,
            "val": 1,
        },
        {
            "devtype": "SL_OL",
            HUB_ID_KEY: "EXCLUDED_HUB",
            DEVICE_ID_KEY: "DEV1",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 1,
            "val": 1,
        },
        {
            "devtype": "UNKNOWN",
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "UNSUPPORTED",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 1,
            "val": 1,
        },
        {
            "devtype": "SL_SPOT",
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "AI_NOT_INCLUDED",
            SUBDEVICE_INDEX_KEY: "s",
            "stat": 3,
        },
    ]:
        send_ws_device_update(ws, payload)

    assert dispatch_calls == []
    assert hass.states._states == {}


def test_on_message_applies_direct_state_updates(monkeypatch):
    cover_type = next(iter(lifesmart_init.COVER_TYPES))
    garage_type = next(iter(lifesmart_init.GARAGE_DOOR_TYPES))
    light_type = next(iter(lifesmart_init.LIGHT_DIMMER_TYPES))
    smart_plug_type = next(iter(lifesmart_init.SMART_PLUG_TYPES))
    ot_type = next(iter(lifesmart_init.OT_SENSOR_TYPES))
    gas_type = next(iter(lifesmart_init.GAS_SENSOR_TYPES))
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "COVER1", "devtype": cover_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "GARAGE1", "devtype": garage_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "LIGHT1", "devtype": light_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "PLUG1", "devtype": smart_plug_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "OT1", "devtype": ot_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "GAS1", "devtype": gas_type},
        ],
    )
    cover_entity = lifesmart_init.generate_entity_id(cover_type, "HUB1", "COVER1", "P1")
    garage_entity = lifesmart_init.generate_entity_id(garage_type, "HUB1", "GARAGE1", "P2")
    light_entity = lifesmart_init.generate_entity_id(light_type, "HUB1", "LIGHT1", "P2")
    plug_switch_entity = lifesmart_init.generate_entity_id(
        smart_plug_type, "HUB1", "PLUG1", "P1"
    )
    plug_sensor_entity = lifesmart_init.generate_entity_id(
        smart_plug_type, "HUB1", "PLUG1", "P3"
    )
    ot_entity = lifesmart_init.generate_entity_id(ot_type, "HUB1", "OT1", "Z")
    gas_entity = lifesmart_init.generate_entity_id(gas_type, "HUB1", "GAS1", "G")

    hass.states.set(cover_entity, "closed", {"current_position": 0})
    hass.states.set(garage_entity, "closed", {"current_position": 0})
    hass.states.set(
        light_entity,
        STATE_ON,
        {
            ATTR_MIN_COLOR_TEMP_KELVIN: 2700,
            ATTR_MAX_COLOR_TEMP_KELVIN: 6500,
            ATTR_COLOR_TEMP_KELVIN: 2700,
        },
    )
    hass.states.set(plug_switch_entity, STATE_OFF, {"friendly_name": "Plug switch"})
    hass.states.set(plug_sensor_entity, 0, {"unit": "kWh"})
    hass.states.set(ot_entity, 0, {"unit": "lx"})
    hass.states.set(gas_entity, 0, {"unit": "ppm"})

    for payload in [
        {
            "devtype": cover_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "COVER1",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 3,
            "val": 0x80 | 45,
        },
        {
            "devtype": garage_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "GARAGE1",
            SUBDEVICE_INDEX_KEY: "P2",
            "type": 3,
            "val": 10,
        },
        {
            "devtype": light_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "LIGHT1",
            SUBDEVICE_INDEX_KEY: "P2",
            "type": 1,
            "val": 0,
        },
        {
            "devtype": smart_plug_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "PLUG1",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 1,
            "val": 1,
        },
        {
            "devtype": smart_plug_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "PLUG1",
            SUBDEVICE_INDEX_KEY: "P3",
            "type": 1,
            "v": 42,
        },
        {
            "devtype": ot_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "OT1",
            SUBDEVICE_INDEX_KEY: "Z",
            "type": 1,
            "v": 99,
        },
        {
            "devtype": gas_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "GAS1",
            SUBDEVICE_INDEX_KEY: "G",
            "type": 1,
            "val": 7,
        },
    ]:
        send_ws_device_update(ws, payload)

    assert dispatch_calls == []
    assert hass.states.get(cover_entity).state == "opening"
    assert hass.states.get(cover_entity).attributes["current_position"] == 45
    assert hass.states.get(garage_entity).state == "closing"
    assert hass.states.get(garage_entity).attributes["current_position"] == 10
    assert hass.states.get(light_entity).state == STATE_ON
    assert hass.states.get(light_entity).attributes[ATTR_COLOR_TEMP_KELVIN] == 6500
    assert hass.states.get(plug_switch_entity).state == STATE_ON
    assert hass.states.get(plug_sensor_entity).state == 42
    assert hass.states.get(ot_entity).state == 99
    assert hass.states.get(gas_entity).state == 7


class FakeBaseClient:
    def __init__(self):
        self.epset_calls = []
        self.epget_calls = []
        self.scene_calls = []

    async def send_epset_async(self, type, val, idx, agt, me):
        self.epset_calls.append((type, val, idx, agt, me))
        return "epset-ok"

    async def get_epget_async(self, agt, me):
        self.epget_calls.append((agt, me))
        return {"value": 1}

    def set_scene_async(self, agt, scene_id):
        self.scene_calls.append((agt, scene_id))
        return {"code": 0}


def test_lifesmart_device_exposes_metadata_and_proxies_client_calls():
    dev = {
        "name": "Living Room",
        "agt": "HUB1",
        "me": "DEV1",
        "devtype": "SL_SC_G",
    }
    client = FakeBaseClient()
    device = lifesmart_init.LifeSmartDevice(dev, client)
    device.entity_id = "binary_sensor.sl_sc_g_hub1_dev1_g"

    assert device.object_id == "binary_sensor.sl_sc_g_hub1_dev1_g"
    assert device.extra_state_attributes == {"agt": "HUB1", "me": "DEV1", "devtype": "SL_SC_G"}
    assert device.name == "Living Room"
    assert device.assumed_state is False
    assert device.should_poll is False
    assert asyncio.run(device.async_lifesmart_epset("0x81", 1, "P1")) == "epset-ok"
    assert asyncio.run(device.async_lifesmart_epget()) == {"value": 1}
    assert asyncio.run(device.async_lifesmart_sceneset("ignored", "ignored")) == 0
    assert client.epset_calls == [("0x81", 1, "P1", "HUB1", "DEV1")]
    assert client.epget_calls == [("HUB1", "DEV1")]
    assert client.scene_calls == [("HUB1", "DEV1")]


def test_states_manager_run_start_and_stop(monkeypatch):
    events = []

    class FakeWS:
        def run_forever(self):
            events.append("run_forever")
            manager._run = False

    manager = lifesmart_init.LifeSmartStatesManager(FakeWS())
    monkeypatch.setattr(lifesmart_init.threading.Thread, "start", lambda self: events.append("thread-start"))
    monkeypatch.setattr(lifesmart_init.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    monkeypatch.setattr(manager, "join", lambda: events.append("join"))

    manager.start_keep_alive()
    assert manager._run is True
    assert events == ["thread-start"]

    manager.run()
    assert events[-2:] == ["run_forever", ("sleep", 10)]

    manager.stop_keep_alive()
    assert manager._run is False
    assert events[-1] == "join"


@pytest.mark.parametrize(
    ("speed", "expected"),
    [
        (10, lifesmart_init.FAN_LOW),
        (30, lifesmart_init.FAN_MEDIUM),
        (64, lifesmart_init.FAN_MEDIUM),
        (65, lifesmart_init.FAN_HIGH),
    ],
)
def test_get_fan_mode(speed, expected):
    assert lifesmart_init.get_fan_mode(speed) == expected


@pytest.mark.parametrize(
    ("device_type", "sub_device", "expected"),
    [
        ("SL_NATURE", lifesmart_init.NATURE_CLIMATE_KEY, lifesmart_init.Platform.CLIMATE),
        ("SL_NATURE", "P4", lifesmart_init.Platform.SENSOR),
        ("SL_NATURE", "P1", lifesmart_init.Platform.SWITCH),
        ("SL_SPOT", "climate_ac", lifesmart_init.Platform.CLIMATE),
        ("SL_SPOT", "remote", lifesmart_init.Platform.REMOTE),
        ("SL_OL", None, lifesmart_init.Platform.SWITCH),
        ("OD_MFRESH_M8088", "O", lifesmart_init.Platform.SWITCH),
        ("SL_JEMA", "P8", lifesmart_init.Platform.SWITCH),
        ("V_485_P", "L1", lifesmart_init.Platform.SWITCH),
        ("SL_P", "P6", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_SC_WA", "WA", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_SC_WA", "V", lifesmart_init.Platform.SENSOR),
        ("SL_P_RM", "P1", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_DF_GG", "GA", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_DF_GG", "T", lifesmart_init.Platform.SENSOR),
        ("SL_SC_CA", "P1", lifesmart_init.Platform.SENSOR),
        ("SL_SC_CN", "P1", lifesmart_init.Platform.SENSOR),
        ("SL_SC_CN", "P3", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_SC_CH", "P3", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_ALM", "P1", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_SC_CM", "P3", lifesmart_init.Platform.SENSOR),
        ("SL_SC_BM", "M", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_SC_BM", "V", lifesmart_init.Platform.SENSOR),
        ("SL_SC_G", "G", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_DOOYA", None, lifesmart_init.Platform.COVER),
        ("SL_SC_THL", "T", lifesmart_init.Platform.SENSOR),
        ("SL_SPOT", "P1", lifesmart_init.Platform.LIGHT),
        ("V_AIR_P", None, lifesmart_init.Platform.CLIMATE),
        ("SL_LK_LS", "BAT", lifesmart_init.Platform.SENSOR),
        ("SL_LK_LS", "EVTLO", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_LK_YL", "EVTOP", lifesmart_init.Platform.SENSOR),
        ("SL_LK_YL", "HISLK", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_OE_DE", "P1", lifesmart_init.Platform.SWITCH),
        ("SL_OE_DE", "P2", lifesmart_init.Platform.SENSOR),
        ("UNKNOWN", None, ""),
    ],
)
def test_get_platform_by_device(device_type, sub_device, expected):
    assert lifesmart_init.get_platform_by_device(device_type, sub_device) == expected


@pytest.mark.parametrize(
    ("device_type", "hub_id", "device_id", "idx", "expected"),
    [
        ("SL_NATURE", "HUB__1", "DEV:1", lifesmart_init.NATURE_CLIMATE_KEY, "climate.sl_nature_hub_1_dev_1_thermostat"),
        ("SL_SPOT", "HUB-1", "DEV@1", "remote", "remote.sl_spot_hub_1_dev_1_remote"),
        ("SL_SPOT", "HUB-1", "DEV@1", "climate_ac", "climate.sl_spot_hub_1_dev_1_climate_ac"),
        ("SL_SC_G", "HUB-1", "DEV1", "G", "binary_sensor.sl_sc_g_hub_1_dev1_g"),
        ("SL_SC_BM", "HUB-1", "DEV1", "V", "sensor.sl_sc_bm_hub_1_dev1_v"),
        ("SL_DOOYA", "HUB-1", "DEV1", None, "cover.sl_dooya_hub_1_dev1"),
        ("SL_LI_WW", "HUB-1", "DEV1", None, "light.sl_li_ww_hub_1_dev1_p1p2"),
        ("V_AIR_P", "HUB-1", "DEV:1", None, "climate.v_air_p_hub_1_dev_1"),
    ],
)
def test_generate_entity_id_module_paths(device_type, hub_id, device_id, idx, expected):
    assert lifesmart_init.generate_entity_id(device_type, hub_id, device_id, idx) == expected


def test_find_device_returns_match_or_none():
    devices = [
        {"agt": "HUB1", "me": "A"},
        {"agt": "HUB2", "me": "B"},
    ]

    assert lifesmart_init._find_device(devices, "HUB2", "B") == {"agt": "HUB2", "me": "B"}
    assert lifesmart_init._find_device(devices, "HUB3", "C") is None
