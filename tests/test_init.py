import asyncio
import importlib
import json
from types import SimpleNamespace

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_MAX_COLOR_TEMP_KELVIN,
    ATTR_MIN_COLOR_TEMP_KELVIN,
)
from homeassistant.const import CONF_REGION, STATE_OFF, STATE_ON

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
    HUB_DEVICE_REGISTRY_ID_KEY,
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    NATURE_CLIMATE_KEY,
    SUBDEVICE_INDEX_KEY,
)

lifesmart_init = importlib.import_module("custom_components.lifesmart")


class FakeConfigEntry:
    def __init__(self, data, options=None, entry_id="entry-1"):
        self.data = data
        self.options = options or {}
        self.entry_id = entry_id
        self.update_listener = None
        self.runtime_data = None

    def add_update_listener(self, listener):
        self.update_listener = listener
        return "listener-token"


def test_lifesmart_type_helper_handles_invalid_values():
    assert lifesmart_init._is_on_type(None) is False
    assert lifesmart_init._is_on_type("not-a-number") is False


def test_refresh_device_availability_uses_cloud_status():
    client = FakeLifeSmartClient("us", "key", "token", "user", "password")
    client.devices_response = [
        {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "ONLINE", "stat": 1},
        {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "OFFLINE", "stat": 0},
        {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "UNKNOWN"},
    ]
    runtime = lifesmart_init.LifeSmartRuntimeData(
        client=client,
        devices=[],
        connected=True,
    )

    asyncio.run(lifesmart_init._async_refresh_device_availability(runtime))

    assert runtime.device_availability == {
        ("HUB1", "ONLINE"): True,
        ("HUB1", "OFFLINE"): False,
    }


def test_scene_discovery_normalizes_filters_and_deduplicates(caplog):
    class SceneClient:
        def __init__(self):
            self.calls = []

        async def get_all_scene_async(self, hub_id):
            self.calls.append(hub_id)
            if hub_id == "HUB2":
                raise RuntimeError("private API failure")
            return [
                {"id": "SCENE1", "name": " Movie Night ", "ignored": "raw"},
                {"id": "SCENE1", "name": "Duplicate"},
                {"id": 7},
                {"name": "Missing ID"},
                "invalid",
            ]

    client = SceneClient()
    scenes = asyncio.run(
        lifesmart_init._async_discover_scenes(
            client, {"HUB3", "HUB2", "HUB1"}, ["HUB3"]
        )
    )

    assert client.calls == ["HUB1", "HUB2"]
    assert scenes == [
        {HUB_ID_KEY: "HUB1", "id": "SCENE1", "name": "Movie Night"},
        {HUB_ID_KEY: "HUB1", "id": "7", "name": "LifeSmart Scene 7"},
    ]
    assert "Unable to retrieve LifeSmart scenes for hub HUB2" in caplog.text


class FakeConfigEntriesManager:
    def __init__(self):
        self.forward_calls = []
        self.reload_calls = []
        self.unload_calls = []
        self.entries = []

    def async_entries(self, domain):
        return self.entries

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
        self.removals = []

    def async_register(self, domain, service, handler, schema=None):
        self.registrations.append((domain, service, handler, schema))

    def async_remove(self, domain, service):
        self.removals.append((domain, service))


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

    async def async_add_executor_job(self, target, *args):
        return target(*args)


class FakeDeviceRegistry:
    def __init__(self):
        self.created = []

    def async_get_or_create(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(id=f"device-{len(self.created)}")


class FakeEntityRegistry:
    def __init__(self, existing=None, entity_ids=None):
        self.existing = set(existing or [])
        self.entity_ids = entity_ids or {}
        self.removed = []

    def async_get_entity_id(self, domain, platform, unique_id):
        return self.entity_ids.get((domain, platform, unique_id))

    def async_get(self, entity_id):
        return entity_id if entity_id in self.existing else None

    def async_remove(self, entity_id):
        self.removed.append(entity_id)
        self.existing.discard(entity_id)


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
        self.stopped = False
        FakeStatesManager.instances.append(self)

    def start_keep_alive(self):
        self.started = True

    def stop_keep_alive(self):
        self.stopped = True


class FakeLifeSmartClient:
    instances = []
    login_response = {"code": "success"}
    devices_response = []
    hubs_response = []
    system_info_response = {}
    timezone_response = {}

    def __init__(self, region, appkey, apptoken, userid, userpassword):
        self.region = region
        self.appkey = appkey
        self.apptoken = apptoken
        self.userid = userid
        self.userpassword = userpassword
        self.login_calls = 0
        self.device_calls = 0
        self.scene_calls = []
        self.service_calls = []
        FakeLifeSmartClient.instances.append(self)

    async def login_async(self):
        self.login_calls += 1
        return self.login_response

    async def get_all_device_async(self):
        self.device_calls += 1
        return self.devices_response

    async def get_all_hubs_async(self):
        return self.hubs_response

    async def get_all_scene_async(self, hub_id):
        self.scene_calls.append(hub_id)
        return []

    async def get_hub_system_info_async(self, hub_id):
        return self.system_info_response

    async def get_hub_timezone_async(self, hub_id):
        return self.timezone_response

    def get_wss_url(self):
        return "wss://example.invalid/wsapp/"

    def generate_wss_auth(self):
        return '{"id": 1, "method": "WbAuth"}'

    async def send_ir_code_async(self, *args):
        self.service_calls.append(("send_ir_code", args))
        return 0


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


def patch_setup_dependencies(monkeypatch, device_registry, entity_registry=None):
    FakeLifeSmartClient.instances.clear()
    FakeWebSocketApp.instances.clear()
    FakeStatesManager.instances.clear()
    entity_registry = entity_registry or FakeEntityRegistry()
    monkeypatch.setattr(lifesmart_init, "LifeSmartClient", FakeLifeSmartClient)
    monkeypatch.setattr(
        lifesmart_init.device_registry, "async_get", lambda hass: device_registry
    )
    monkeypatch.setattr(
        lifesmart_init.entity_registry, "async_get", lambda hass: entity_registry
    )
    monkeypatch.setattr(lifesmart_init.websocket, "WebSocketApp", FakeWebSocketApp)
    monkeypatch.setattr(lifesmart_init, "LifeSmartStatesManager", FakeStatesManager)


def setup_entry_for_ws_tests(
    monkeypatch, devices, options=None, entity_registry_instance=None
):
    hass = FakeHass()
    config_entry = make_config_entry(options=options)
    device_reg = FakeDeviceRegistry()
    dispatch_calls = []

    FakeLifeSmartClient.login_response = {"code": "success"}
    FakeLifeSmartClient.devices_response = devices
    FakeLifeSmartClient.hubs_response = []
    FakeLifeSmartClient.system_info_response = {}
    FakeLifeSmartClient.timezone_response = {}
    patch_setup_dependencies(monkeypatch, device_reg, entity_registry_instance)
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


def test_setup_initializes_device_availability_from_cloud_status(monkeypatch):
    _hass, entry, _ws, _dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "ONLINE", "stat": 1},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "OFFLINE", "stat": 0},
        ],
    )

    assert entry.runtime_data.device_availability == {
        ("HUB1", "ONLINE"): True,
        ("HUB1", "OFFLINE"): False,
    }


def test_websocket_device_status_updates_availability(monkeypatch):
    _hass, entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "DEV1",
                "devtype": "SL_SW_IF1",
                "stat": 1,
            }
        ],
    )

    send_ws_device_update(
        ws,
        {
            "devtype": "SL_SW_IF1",
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "DEV1",
            SUBDEVICE_INDEX_KEY: "s",
            "v": 2,
        },
    )
    assert entry.runtime_data.device_availability[("HUB1", "DEV1")] is False

    send_ws_device_update(
        ws,
        {
            "devtype": "SL_SW_IF1",
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "DEV1",
            SUBDEVICE_INDEX_KEY: "s",
            "v": 1,
        },
    )
    assert entry.runtime_data.device_availability[("HUB1", "DEV1")] is True
    assert dispatch_calls == []


def test_websocket_hub_offline_marks_child_devices_unavailable(monkeypatch):
    _hass, entry, ws, _dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "DEV1", "stat": 1},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "DEV2", "stat": 1},
            {HUB_ID_KEY: "HUB2", DEVICE_ID_KEY: "DEV3", "stat": 1},
        ],
    )

    send_ws_device_update(
        ws,
        {
            "devtype": "agt",
            HUB_ID_KEY: "HUB1",
            SUBDEVICE_INDEX_KEY: "s",
            "v": 2,
        },
    )

    assert entry.runtime_data.device_availability == {
        ("HUB1", "DEV1"): False,
        ("HUB1", "DEV2"): False,
        ("HUB2", "DEV3"): True,
    }


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
    FakeLifeSmartClient.hubs_response = []
    FakeLifeSmartClient.system_info_response = {}
    FakeLifeSmartClient.timezone_response = {}
    FakeLifeSmartClient.devices_response = [
        {HUB_ID_KEY: "HUB1"},
        {HUB_ID_KEY: "HUB2"},
        {HUB_ID_KEY: "HUB1"},
    ]
    patch_setup_dependencies(monkeypatch, device_reg)

    assert asyncio.run(lifesmart_init.async_setup(hass, {})) is True
    result = asyncio.run(lifesmart_init.async_setup_entry(hass, config_entry))

    assert result is True
    client = FakeLifeSmartClient.instances[0]
    assert (
        client.region,
        client.appkey,
        client.apptoken,
        client.userid,
        client.userpassword,
    ) == (
        "opt-region",
        "opt-appkey",
        "data-apptoken",
        "data-user",
        "data-password",
    )
    assert client.login_calls == 1
    assert client.device_calls == 1
    runtime = config_entry.runtime_data
    assert runtime.client is client
    stored_devices = runtime.devices
    assert [device[HUB_ID_KEY] for device in stored_devices] == [
        "HUB1",
        "HUB2",
        "HUB1",
    ]
    assert stored_devices[0][HUB_DEVICE_REGISTRY_ID_KEY] == stored_devices[2][
        HUB_DEVICE_REGISTRY_ID_KEY
    ]
    assert stored_devices[0][HUB_DEVICE_REGISTRY_ID_KEY] != stored_devices[1][
        HUB_DEVICE_REGISTRY_ID_KEY
    ]
    assert runtime.exclude_devices == []
    assert runtime.exclude_hubs == []
    assert runtime.ai_include_hubs == []
    assert runtime.ai_include_items == []
    assert runtime.scenes == []
    assert runtime.update_listener == "listener-token"
    assert {hub[HUB_ID_KEY] for hub in runtime.hubs} == {"HUB1", "HUB2"}
    assert client.scene_calls == ["HUB1", "HUB2"]
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
    manager = runtime.state_manager
    assert isinstance(manager, FakeStatesManager)
    assert manager.started is True
    ws = FakeWebSocketApp.instances[0]
    assert ws.url == "wss://example.invalid/wsapp/"
    ws.on_open(ws)
    assert ws.sent == ['{"id": 1, "method": "WbAuth"}']
    assert runtime.connected is True
    ws.on_error(ws, RuntimeError("offline"))
    assert runtime.connected is False
    assert runtime.last_error == "RuntimeError"


def test_async_setup_entry_adds_cloud_hub_metadata(monkeypatch):
    hass = FakeHass()
    config_entry = make_config_entry()
    device_reg = FakeDeviceRegistry()
    FakeLifeSmartClient.login_response = {"code": "success"}
    FakeLifeSmartClient.devices_response = []
    FakeLifeSmartClient.hubs_response = [
        {
            HUB_ID_KEY: "HUB1",
            "name": "Living Room Hub",
            "agt_ver": "1.2.3",
            "stat": 1,
        }
    ]
    FakeLifeSmartClient.system_info_response = {
        "mac": "AA-BB-CC-DD-EE-FF",
        "ip": "192.168.1.20",
    }
    FakeLifeSmartClient.timezone_response = {"tmzone": 7}
    patch_setup_dependencies(monkeypatch, device_reg)

    assert asyncio.run(lifesmart_init.async_setup_entry(hass, config_entry)) is True

    assert config_entry.runtime_data.hubs == [
        {
            **FakeLifeSmartClient.hubs_response[0],
            "mac": "aa:bb:cc:dd:ee:ff",
            "ip": "192.168.1.20",
            "tmzone": 7,
        }
    ]
    assert device_reg.created == [
        {
            "config_entry_id": "entry-1",
            "identifiers": {(DOMAIN, "HUB1")},
            "connections": {("mac", "aa:bb:cc:dd:ee:ff")},
            "name": "Living Room Hub",
            "manufacturer": "LifeSmart",
            "model": "Hub",
            "sw_version": "1.2.3",
        }
    ]


def test_async_setup_entry_ignores_invalid_hub_network_metadata(monkeypatch):
    hass = FakeHass()
    config_entry = make_config_entry()
    device_reg = FakeDeviceRegistry()
    FakeLifeSmartClient.login_response = {"code": "success"}
    FakeLifeSmartClient.devices_response = []
    FakeLifeSmartClient.hubs_response = [{HUB_ID_KEY: "HUB1"}]
    FakeLifeSmartClient.system_info_response = {
        "mac": "not-a-mac",
        "ip": "not-an-ip",
    }
    FakeLifeSmartClient.timezone_response = {"code": 500}
    patch_setup_dependencies(monkeypatch, device_reg)

    assert asyncio.run(lifesmart_init.async_setup_entry(hass, config_entry)) is True

    assert config_entry.runtime_data.hubs == [{HUB_ID_KEY: "HUB1"}]
    assert "connections" not in device_reg.created[0]


def test_central_service_handler_resolves_runtime_by_device():
    hass = FakeHass()
    entry = make_config_entry()
    client = FakeLifeSmartClient("us", "key", "token", "user", "password")
    entry.runtime_data = lifesmart_init.LifeSmartRuntimeData(
        client=client,
        devices=[{HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "DEVICE1"}],
        connected=True,
    )
    hass.config_entries.entries = [entry]
    call = SimpleNamespace(
        service="send_ir_code",
        data={HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "DEVICE1", "ir_code": "123"},
    )

    asyncio.run(lifesmart_init._async_call_lifesmart_service(hass, call))

    assert client.service_calls == [
        (
            "send_ir_code",
            (
                "HUB1",
                "DEVICE1",
                '[{"param": {"data": "123", "type": 1}}]',
            ),
        )
    ]


def test_central_service_handler_rejects_unknown_target():
    hass = FakeHass()
    hass.config_entries.entries = []
    call = SimpleNamespace(
        service="scene_set", data={HUB_ID_KEY: "missing", "id": "scene"}
    )

    with pytest.raises(lifesmart_init.ServiceValidationError):
        asyncio.run(lifesmart_init._async_call_lifesmart_service(hass, call))


def test_central_service_handler_rejects_ambiguous_target():
    hass = FakeHass()
    entries = [make_config_entry() for _index in range(2)]
    for entry in entries:
        entry.runtime_data = lifesmart_init.LifeSmartRuntimeData(
            client=object(),
            devices=[{HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "DEVICE1"}],
        )
    hass.config_entries.entries = entries

    with pytest.raises(lifesmart_init.ServiceValidationError):
        lifesmart_init._runtime_for_service(
            hass, {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "DEVICE1"}
        )


def test_central_scene_service_resolves_hub_without_devices():
    entry = make_config_entry()
    entry.runtime_data = lifesmart_init.LifeSmartRuntimeData(
        client=object(),
        devices=[],
        hubs=[{HUB_ID_KEY: "HUB1"}],
        scenes=[{HUB_ID_KEY: "HUB1", "id": "SCENE1"}],
    )
    hass = FakeHass()
    hass.config_entries.entries = [entry]

    assert (
        lifesmart_init._runtime_for_service(hass, {HUB_ID_KEY: "HUB1"})
        is entry.runtime_data
    )


@pytest.mark.parametrize(
    ("service", "data", "method", "expected_args"),
    [
        (
            "send_keys",
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "DEVICE1",
                "ai": "ai-1",
                "category": "tv",
                "brand": "brand",
                "keys": ["power"],
            },
            "send_ir_key_async",
            ("HUB1", "ai-1", "DEVICE1", "tv", "brand", ["power"]),
        ),
        (
            "send_ackeys",
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "DEVICE1",
                "ai": "ai-1",
                "category": "ac",
                "brand": "brand",
                "keys": "power",
                "idx": "1",
                "power": 1,
                "mode": 2,
                "temp": 24,
                "wind": 3,
                "swing": 4,
            },
            "send_ir_ackey_async",
            (
                "HUB1",
                "ai-1",
                "DEVICE1",
                "ac",
                "brand",
                "power",
                "1",
                1,
                2,
                24,
                3,
                4,
            ),
        ),
        (
            "scene_set",
            {HUB_ID_KEY: "HUB1", "id": "scene-1"},
            "set_scene_async",
            ("HUB1", "scene-1"),
        ),
    ],
)
def test_central_service_handler_dispatches_all_actions(
    service, data, method, expected_args
):
    calls = []

    async def service_method(*args):
        calls.append(args)
        return {"code": "success"}

    client = SimpleNamespace(**{method: service_method})
    entry = make_config_entry()
    entry.runtime_data = lifesmart_init.LifeSmartRuntimeData(
        client=client,
        devices=[{HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "DEVICE1"}],
    )
    hass = FakeHass()
    hass.config_entries.entries = [entry]

    asyncio.run(
        lifesmart_init._async_call_lifesmart_service(
            hass, SimpleNamespace(service=service, data=data)
        )
    )

    assert calls == [expected_args]


@pytest.mark.parametrize("response", [1, {"code": 500}])
def test_central_service_handler_reports_rejected_action(response):
    async def set_scene_async(*args):
        return response

    entry = make_config_entry()
    entry.runtime_data = lifesmart_init.LifeSmartRuntimeData(
        client=SimpleNamespace(set_scene_async=set_scene_async),
        devices=[{HUB_ID_KEY: "HUB1"}],
    )
    hass = FakeHass()
    hass.config_entries.entries = [entry]
    call = SimpleNamespace(
        service="scene_set", data={HUB_ID_KEY: "HUB1", "id": "scene-1"}
    )

    with pytest.raises(lifesmart_init.HomeAssistantError) as error:
        asyncio.run(lifesmart_init._async_call_lifesmart_service(hass, call))

    assert error.value.translation_key == "service_action_rejected"


def test_central_service_handler_wraps_client_error():
    async def set_scene_async(*args):
        raise RuntimeError("private API failure")

    entry = make_config_entry()
    entry.runtime_data = lifesmart_init.LifeSmartRuntimeData(
        client=SimpleNamespace(set_scene_async=set_scene_async),
        devices=[{HUB_ID_KEY: "HUB1"}],
    )
    hass = FakeHass()
    hass.config_entries.entries = [entry]
    call = SimpleNamespace(
        service="scene_set", data={HUB_ID_KEY: "HUB1", "id": "scene-1"}
    )

    with pytest.raises(lifesmart_init.HomeAssistantError) as error:
        asyncio.run(lifesmart_init._async_call_lifesmart_service(hass, call))

    assert error.value.translation_key == "service_action_failed"
    assert isinstance(error.value.__cause__, RuntimeError)


def test_device_via_info_uses_registry_id_when_supported(monkeypatch):
    """New Home Assistant releases link child devices by registry ID."""
    monkeypatch.setitem(
        lifesmart_init.DeviceInfo.__annotations__, "via_device_id", str | None
    )

    assert lifesmart_init.device_via_info(
        {HUB_DEVICE_REGISTRY_ID_KEY: "hub-device-id"}, "HUB1"
    ) == {"via_device_id": "hub-device-id"}


def test_device_via_info_falls_back_for_older_home_assistant(monkeypatch):
    """Older Home Assistant releases still require the identifier tuple."""
    monkeypatch.delitem(
        lifesmart_init.DeviceInfo.__annotations__, "via_device_id", raising=False
    )

    assert lifesmart_init.device_via_info(
        {HUB_DEVICE_REGISTRY_ID_KEY: "hub-device-id"}, "HUB1"
    ) == {"via_device": (DOMAIN, "HUB1")}


def test_migrate_legacy_device_identifiers_preserves_registry_device():
    """Legacy invalid identifiers are rewritten on their existing device entry."""
    owned_device = SimpleNamespace(
        id="owned-device",
        config_entries={"entry-1"},
        identifiers={(DOMAIN, "HUB1", "DEV1"), ("other", "identifier")},
    )
    unrelated_device = SimpleNamespace(
        id="unrelated-device",
        config_entries={"entry-2"},
        identifiers={(DOMAIN, "HUB1", "DEV1")},
    )

    class MigrationRegistry:
        devices = {
            owned_device.id: owned_device,
            unrelated_device.id: unrelated_device,
        }

        def __init__(self):
            self.updated = []

        def async_update_device(self, device_id, **changes):
            self.updated.append((device_id, changes))

    registry = MigrationRegistry()
    lifesmart_init._migrate_legacy_device_identifiers(
        registry,
        "entry-1",
        [{HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "DEV1"}],
    )

    assert registry.updated == [
        (
            "owned-device",
            {
                "new_identifiers": {
                    (DOMAIN, "HUB1:DEV1"),
                    ("other", "identifier"),
                }
            },
        )
    ]


@pytest.mark.parametrize(
    ("stored_region", "expected_region"),
    [
        ("AME", "us"),
        ("EUR", "eur"),
        ("JAP", "jp"),
        ("APZ", "apz"),
        ("cn0", "cn0"),
        ("us", "us"),
        ("country:th", "apz"),
    ],
)
def test_async_setup_entry_supports_existing_region_values(
    monkeypatch, stored_region, expected_region
):
    """Existing entries may store legacy service codes or direct API regions."""
    hass = FakeHass()
    config_entry = make_config_entry(options={CONF_REGION: stored_region})
    device_reg = FakeDeviceRegistry()
    FakeLifeSmartClient.login_response = {"code": "success"}
    FakeLifeSmartClient.devices_response = []
    patch_setup_dependencies(monkeypatch, device_reg)

    result = asyncio.run(lifesmart_init.async_setup_entry(hass, config_entry))

    assert result is True
    assert FakeLifeSmartClient.instances[0].region == expected_region


def test_cleanup_legacy_doorlock_history_binary_sensor(monkeypatch):
    legacy_entity_id = "binary_sensor.sl_lk_yl_hub_1_lock_1_hislk"
    ent_reg = FakeEntityRegistry(existing={legacy_entity_id})
    monkeypatch.setattr(
        lifesmart_init.entity_registry, "async_get", lambda hass: ent_reg
    )

    lifesmart_init._cleanup_legacy_doorlock_history_entities(
        object(),
        [
            {
                "devtype": "SL_LK_YL",
                HUB_ID_KEY: "HUB-1",
                DEVICE_ID_KEY: "LOCK:1",
                "data": {"HISLK": {"val": 0x1001}},
            },
            {
                "devtype": "SL_LK_YL",
                HUB_ID_KEY: "HUB-1",
                DEVICE_ID_KEY: "LOCK:2",
                "data": {"EVTLO": {"val": 0x1001}},
            },
        ],
    )

    assert ent_reg.removed == [legacy_entity_id]


def test_async_setup_entry_raises_when_login_fails(monkeypatch):
    hass = FakeHass()
    config_entry = make_config_entry()
    device_reg = FakeDeviceRegistry()
    FakeLifeSmartClient.login_response = {"code": "failure", "message": "bad auth"}
    FakeLifeSmartClient.devices_response = []
    patch_setup_dependencies(monkeypatch, device_reg)

    with pytest.raises(lifesmart_init.ConfigEntryAuthFailed):
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
    FakeLifeSmartClient.devices_response = {
        "code": 500,
        "message": "device fetch failed",
    }
    patch_setup_dependencies(monkeypatch, device_reg)

    with pytest.raises(lifesmart_init.ConfigEntryNotReady):
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
    manager = FakeStatesManager(ws=object())
    listener_removals = []
    config_entry.runtime_data = lifesmart_init.LifeSmartRuntimeData(
        client=None,
        devices=[],
        state_manager=manager,
        update_listener=lambda: listener_removals.append("removed"),
    )

    result = asyncio.run(lifesmart_init.async_unload_entry(hass, config_entry))

    assert result is True
    assert hass.config_entries.unload_calls == [
        (config_entry, tuple(lifesmart_init.SUPPORTED_PLATFORMS))
    ]
    assert manager.stopped is True
    assert listener_removals == ["removed"]
    assert hass.services.removals == []


def test_async_unload_entry_keeps_runtime_running_when_platform_unload_fails():
    hass = FakeHass()

    async def fail_unload(_entry, _platforms):
        return False

    hass.config_entries.async_unload_platforms = fail_unload
    config_entry = FakeConfigEntry(data={})
    manager = FakeStatesManager(ws=object())
    listener_removals = []
    config_entry.runtime_data = lifesmart_init.LifeSmartRuntimeData(
        client=None,
        devices=[],
        state_manager=manager,
        update_listener=lambda: listener_removals.append("removed"),
    )

    assert asyncio.run(lifesmart_init.async_unload_entry(hass, config_entry)) is False
    assert manager.stopped is False
    assert listener_removals == []


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
                    SUBDEVICE_INDEX_KEY: next(
                        iter(lifesmart_init.SUPPORTED_SUB_SWITCH_TYPES)
                    ),
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
                SUBDEVICE_INDEX_KEY: next(
                    iter(lifesmart_init.SUPPORTED_SUB_SWITCH_TYPES)
                ),
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
    plug_entity = lifesmart_init.generate_entity_id(
        smart_plug_type, "HUB1", "PLUG1", "P2"
    )
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

    assert [call[0] for call in dispatch_calls] == [
        f"{lifesmart_init.LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}"
        for entity_id in (cover_entity, light_entity, plug_entity, water_entity)
    ]


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
        ("SL_P", "P1"),
        ("SL_JEMA", "P1"),
        ("SL_JEMA", "P8"),
        ("SL_JEMA", "P10"),
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
        ("SL_CAM", "M"),
        ("SL_CAM", "V"),
        ("ELIQ_EM", "EPA"),
        ("V_DLT_645_P", "EE"),
        ("V_485_P", "CO2PPM"),
        ("V_485_P", "EPF2"),
        ("V_485_P", "PM10"),
        ("OD_MFRESH_M8088", "PM"),
        ("SL_SC_BE", "P9"),
        ("SL_SPOT", "P1"),
        ("SL_P_IR", "P2"),
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
    expected_dispatch_calls = [
        (f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{expected_entity_id}", payload)
    ]
    related_sub_device_key = None
    if sub_device_key == "EVTLO":
        related_sub_device_key = "HISLK"
    elif sub_device_key == "HISLK":
        related_sub_device_key = "EVTLO"
    if related_sub_device_key is not None:
        related_entity_id = lifesmart_init.generate_entity_id(
            device_type, "HUB1", "DEV1", related_sub_device_key
        )
        related_payload = dict(payload)
        related_payload[SUBDEVICE_INDEX_KEY] = related_sub_device_key
        expected_dispatch_calls.append(
            (f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{related_entity_id}", related_payload)
        )
    assert dispatch_calls == expected_dispatch_calls
    assert hass.states._states == {}


def test_on_message_dispatches_camera_status_bits(monkeypatch):
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "CAM1",
                "devtype": "SL_CAM",
            }
        ],
    )
    payload = {
        "devtype": "SL_CAM",
        HUB_ID_KEY: "HUB1",
        DEVICE_ID_KEY: "CAM1",
        SUBDEVICE_INDEX_KEY: "CFST",
        "val": 0b101,
    }

    send_ws_device_update(ws, payload)

    expected_entity_ids = [
        lifesmart_init.generate_entity_id("SL_CAM", "HUB1", "CAM1", status_key)
        for status_key in lifesmart_init.SMART_CAMERA_STATUS_BINARY_KEYS
    ]
    assert dispatch_calls == [
        (f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", payload)
        for entity_id in expected_entity_ids
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
    monkeypatch.setattr(
        lifesmart_init, "is_nature_thermostat", lambda raw_device: False
    )
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
    garage_entity = lifesmart_init.generate_entity_id(
        garage_type, "HUB1", "GARAGE1", "P2"
    )
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

    assert [call[0] for call in dispatch_calls] == [
        f"{lifesmart_init.LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}"
        for entity_id in (
            cover_entity,
            garage_entity,
            light_entity,
            plug_switch_entity,
            plug_sensor_entity,
            ot_entity,
            gas_entity,
        )
    ]


def test_on_message_updates_user_renamed_registry_entity(monkeypatch):
    """Direct websocket updates resolve the current entity registry ID."""
    smart_plug_type = next(iter(lifesmart_init.SMART_PLUG_TYPES))
    unique_id = lifesmart_init.generate_entity_id(
        smart_plug_type, "HUB1", "PLUG1", "P1"
    )
    renamed_entity_id = "switch.office_plug"
    ent_reg = FakeEntityRegistry(
        entity_ids={("switch", DOMAIN, unique_id): renamed_entity_id}
    )
    hass, _entry, ws, _dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {
                HUB_ID_KEY: "HUB1",
                DEVICE_ID_KEY: "PLUG1",
                "devtype": smart_plug_type,
            }
        ],
        entity_registry_instance=ent_reg,
    )
    hass.states.set(renamed_entity_id, STATE_OFF, {"friendly_name": "Office"})

    send_ws_device_update(
        ws,
        {
            "devtype": smart_plug_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "PLUG1",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 1,
            "val": 1,
        },
    )

    assert _dispatch_calls[0][0] == (
        f"{lifesmart_init.LIFESMART_SIGNAL_UPDATE_ENTITY}_{unique_id}"
    )


def test_on_message_skips_direct_state_updates_for_missing_entities(monkeypatch):
    cover_type = next(iter(lifesmart_init.COVER_TYPES))
    light_type = next(iter(lifesmart_init.LIGHT_DIMMER_TYPES))
    smart_plug_type = next(iter(lifesmart_init.SMART_PLUG_TYPES))
    ot_type = next(iter(lifesmart_init.OT_SENSOR_TYPES))
    gas_type = next(iter(lifesmart_init.GAS_SENSOR_TYPES))
    water_type = next(iter(lifesmart_init.WATER_LEAK_SENSOR_TYPES))
    hass, _entry, ws, dispatch_calls = setup_entry_for_ws_tests(
        monkeypatch,
        devices=[
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "COVER1", "devtype": cover_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "LIGHT1", "devtype": light_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "PLUG1", "devtype": smart_plug_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "OT1", "devtype": ot_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "GAS1", "devtype": gas_type},
            {HUB_ID_KEY: "HUB1", DEVICE_ID_KEY: "WATER1", "devtype": water_type},
        ],
    )

    for payload in [
        {
            "devtype": cover_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "COVER1",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": 3,
            "val": 45,
        },
        {
            "devtype": light_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "LIGHT1",
            SUBDEVICE_INDEX_KEY: "P1",
            "type": "0x81",
            "val": 120,
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
            "type": "0x80",
            "val": 0,
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
        {
            "devtype": water_type,
            HUB_ID_KEY: "HUB1",
            DEVICE_ID_KEY: "WATER1",
            SUBDEVICE_INDEX_KEY: "V",
            "type": 1,
            "v": 80,
        },
    ]:
        send_ws_device_update(ws, payload)

    assert len(dispatch_calls) == 8
    assert hass.states._states == {}


class FakeBaseClient:
    def __init__(self):
        self.epset_calls = []
        self.epget_calls = []

    async def send_epset_async(self, type, val, idx, agt, me):
        self.epset_calls.append((type, val, idx, agt, me))
        return "epset-ok"

    async def get_epget_async(self, agt, me):
        self.epget_calls.append((agt, me))
        return {"value": 1}


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
    assert device.extra_state_attributes == {
        "agt": "HUB1",
        "me": "DEV1",
        "devtype": "SL_SC_G",
    }
    assert device.name == "Living Room"
    assert device.assumed_state is False
    assert device.should_poll is False
    assert asyncio.run(device.async_lifesmart_epset("0x81", 1, "P1")) == "epset-ok"
    assert asyncio.run(device.async_lifesmart_epget()) == {"value": 1}
    assert client.epset_calls == [("0x81", 1, "P1", "HUB1", "DEV1")]
    assert client.epget_calls == [("HUB1", "DEV1")]


def test_states_manager_run_start_and_stop(monkeypatch):
    events = []

    class FakeWS:
        def run_forever(self):
            events.append("run_forever")
            manager._stop_event.set()

        def close(self):
            events.append("close")

    manager = lifesmart_init.LifeSmartStatesManager(FakeWS())
    monkeypatch.setattr(
        lifesmart_init.threading.Thread,
        "start",
        lambda self: events.append("thread-start"),
    )
    monkeypatch.setattr(manager, "is_alive", lambda: True)
    monkeypatch.setattr(manager, "join", lambda: events.append("join"))

    manager.start_keep_alive()
    assert manager._stop_event.is_set() is False
    assert events == ["thread-start"]

    manager.run()
    assert events[-1] == "run_forever"

    manager.stop_keep_alive()
    assert manager._stop_event.is_set() is True
    assert events[-2:] == ["close", "join"]


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
        (
            "SL_NATURE",
            lifesmart_init.NATURE_CLIMATE_KEY,
            lifesmart_init.Platform.CLIMATE,
        ),
        ("SL_NATURE", "P4", lifesmart_init.Platform.SENSOR),
        ("SL_NATURE", "P1", lifesmart_init.Platform.SWITCH),
        ("SL_SPOT", "climate_ac", lifesmart_init.Platform.CLIMATE),
        ("SL_SPOT", "remote", lifesmart_init.Platform.REMOTE),
        ("SL_P_IR", "remote", lifesmart_init.Platform.REMOTE),
        ("SL_OL", None, lifesmart_init.Platform.SWITCH),
        ("OD_MFRESH_M8088", "O", lifesmart_init.Platform.SWITCH),
        ("SL_JEMA", "P8", lifesmart_init.Platform.SWITCH),
        ("SL_JEMA", "P10", lifesmart_init.Platform.SWITCH),
        ("V_485_P", "L1", lifesmart_init.Platform.SWITCH),
        ("SL_P", "P1", lifesmart_init.Platform.SENSOR),
        ("SL_JEMA", "P1", lifesmart_init.Platform.SENSOR),
        ("SL_P", "P6", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_SC_WA", "WA", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_SC_WA", "V", lifesmart_init.Platform.SENSOR),
        ("SL_P_RM", "P1", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_DF_GG", "GA", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_DF_GG", "T", lifesmart_init.Platform.SENSOR),
        ("SL_SC_CA", "P1", lifesmart_init.Platform.SENSOR),
        ("SL_SC_CN", "P1", lifesmart_init.Platform.SENSOR),
        ("SL_SC_CN", "P3", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_P_IR", "P2", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_SC_CH", "P3", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_ALM", "P1", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_CAM", "M", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_CAM", "V", lifesmart_init.Platform.SENSOR),
        ("SL_CAM", "CFST_EXTERNAL_POWER", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_CAM", "CFST_ROTARY_PTZ", lifesmart_init.Platform.BINARY_SENSOR),
        ("SL_CAM", "CFST_ROTATING", lifesmart_init.Platform.BINARY_SENSOR),
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
        ("SL_LK_YL", "HISLK", lifesmart_init.Platform.SENSOR),
        ("SL_OE_DE", "P1", lifesmart_init.Platform.SWITCH),
        ("SL_OE_DE", "P2", lifesmart_init.Platform.SENSOR),
        ("V_IND_S", "P8", lifesmart_init.Platform.SWITCH),
        ("UNKNOWN", None, ""),
    ],
)
def test_get_platform_by_device(device_type, sub_device, expected):
    assert lifesmart_init.get_platform_by_device(device_type, sub_device) == expected


@pytest.mark.parametrize(
    ("device_type", "hub_id", "device_id", "idx", "expected"),
    [
        (
            "SL_NATURE",
            "HUB__1",
            "DEV:1",
            lifesmart_init.NATURE_CLIMATE_KEY,
            "climate.sl_nature_hub_1_dev_1_thermostat",
        ),
        ("SL_SPOT", "HUB-1", "DEV@1", "remote", "remote.sl_spot_hub_1_dev_1_remote"),
        ("SL_P_IR", "HUB-1", "DEV@1", "remote", "remote.sl_p_ir_hub_1_dev_1_remote"),
        (
            "SL_SPOT",
            "HUB-1",
            "DEV@1",
            "climate_ac",
            "climate.sl_spot_hub_1_dev_1_climate_ac",
        ),
        ("SL_SC_G", "HUB-1", "DEV1", "G", "binary_sensor.sl_sc_g_hub_1_dev1_g"),
        ("SL_SC_BM", "HUB-1", "DEV1", "V", "sensor.sl_sc_bm_hub_1_dev1_v"),
        ("SL_CAM", "HUB-1", "CAM1", "M", "binary_sensor.sl_cam_hub_1_cam1_m"),
        (
            "SL_CAM",
            "HUB-1",
            "CAM1",
            "CFST_EXTERNAL_POWER",
            "binary_sensor.sl_cam_hub_1_cam1_cfst_external_power",
        ),
        ("SL_DOOYA", "HUB-1", "DEV1", None, "cover.sl_dooya_hub_1_dev1"),
        ("SL_LI_WW", "HUB-1", "DEV1", None, "light.sl_li_ww_hub_1_dev1_p1p2"),
        ("V_AIR_P", "HUB-1", "DEV:1", None, "climate.v_air_p_hub_1_dev_1"),
    ],
)
def test_generate_entity_id_module_paths(device_type, hub_id, device_id, idx, expected):
    assert (
        lifesmart_init.generate_entity_id(device_type, hub_id, device_id, idx)
        == expected
    )


def test_find_device_returns_match_or_none():
    devices = [
        {"agt": "HUB1", "me": "A"},
        {"agt": "HUB2", "me": "B"},
    ]

    assert lifesmart_init._find_device(devices, "HUB2", "B") == {
        "agt": "HUB2",
        "me": "B",
    }
    assert lifesmart_init._find_device(devices, "HUB3", "C") is None
