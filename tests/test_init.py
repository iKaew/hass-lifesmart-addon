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
