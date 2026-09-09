import asyncio
import importlib
from unittest.mock import AsyncMock, Mock

import pytest

config_flow_module = importlib.import_module("custom_components.lifesmart.config_flow")


def local_input():
    return {"host": "192.0.2.10", "port": 8888, "local_password": "secret"}


@pytest.mark.parametrize("failure", ["login", "auth", "devices", "invalid_devices", "cancel"])
def test_local_validation_closes_client_on_every_failure(monkeypatch, failure):
    client = Mock(
        login_async=AsyncMock(return_value={"code": "success"}),
        get_all_device_async=AsyncMock(return_value=[]),
        async_close=AsyncMock(),
    )
    expected = config_flow_module.LifeSmartCannotConnect
    if failure == "login":
        client.login_async.side_effect = TimeoutError()
    elif failure == "auth":
        client.login_async.return_value = {"code": "failure"}
        expected = config_flow_module.LifeSmartInvalidAuth
    elif failure == "devices":
        client.get_all_device_async.side_effect = ConnectionError()
    elif failure == "invalid_devices":
        client.get_all_device_async.return_value = {"error": "unavailable"}
    else:
        client.login_async.side_effect = asyncio.CancelledError()
        expected = asyncio.CancelledError
    monkeypatch.setattr(config_flow_module, "LocalLifeSmartClient", Mock(return_value=client))

    with pytest.raises(expected):
        asyncio.run(config_flow_module.validate_local_input(object(), local_input()))

    client.async_close.assert_awaited_once()
    if failure in {"login", "auth", "cancel"}:
        client.get_all_device_async.assert_not_awaited()


@pytest.mark.parametrize("error,code", [
    (config_flow_module.LifeSmartCannotConnect, "cannot_connect"),
    (RuntimeError, "unknown"),
])
def test_local_setup_maps_validation_errors(monkeypatch, error, code):
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.hass = object()
    flow.async_show_form = lambda **kwargs: kwargs
    flow.async_create_entry = Mock()
    monkeypatch.setattr(config_flow_module, "validate_local_input", AsyncMock(side_effect=error()))

    result = asyncio.run(flow.async_step_local(local_input()))

    assert result["step_id"] == "local"
    assert result["errors"] == {"base": code}
    flow.async_create_entry.assert_not_called()


def test_local_discovery_failure_still_allows_manual_setup(monkeypatch):
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.hass = object()
    flow.async_show_form = lambda **kwargs: kwargs
    monkeypatch.setattr(config_flow_module, "async_discover_local_hubs", AsyncMock(side_effect=OSError("broadcast unavailable")))

    result = asyncio.run(flow.async_step_local())

    assert result["errors"] == {}
    validated = result["data_schema"]({"host": "192.0.2.10"})
    assert validated["port"] == 8888
    assert validated["local_password"] == "admin"


@pytest.mark.parametrize("port", [0, -1, 65536, "invalid"])
def test_local_schema_rejects_invalid_ports(port):
    with pytest.raises(config_flow_module.vol.Invalid):
        config_flow_module.vol.Schema(config_flow_module.LOCAL_DATA_SCHEMA)(local_input() | {"port": port})


@pytest.mark.parametrize("error,code", [
    (config_flow_module.LifeSmartInvalidAuth, "invalid_auth"),
    (config_flow_module.LifeSmartCannotConnect, "cannot_connect"),
])
def test_local_options_failure_does_not_save_settings(monkeypatch, error, code):
    flow = make_options_flow(FakeConfigEntry(data=local_input() | {"connection_type": "local"}))
    flow.async_create_entry = Mock()
    monkeypatch.setattr(config_flow_module, "validate_local_input", AsyncMock(side_effect=error()))

    result = asyncio.run(flow.async_step_user(local_input()))

    assert result["step_id"] == "local"
    assert result["errors"] == {"base": code}
    flow.async_create_entry.assert_not_called()


def test_local_options_saves_validated_settings_without_cloud_validation(monkeypatch):
    flow = make_options_flow(FakeConfigEntry(data=local_input() | {"connection_type": "local"}))
    validator = AsyncMock(return_value={"title": "Local Hub", "unique_id": "local-HUB1"})
    cloud_validator = AsyncMock(side_effect=AssertionError("unexpected cloud validation"))
    monkeypatch.setattr(config_flow_module, "validate_local_input", validator)
    monkeypatch.setattr(config_flow_module, "validate_input", cloud_validator)
    updated = local_input() | {"host": "192.0.2.20", "port": 9999}

    result = asyncio.run(flow.async_step_user(updated.copy()))

    assert result["type"] == "create_entry"
    assert result["data"] == updated | {"connection_type": "local", "name": "Local Hub"}
    validator.assert_awaited_once()
    cloud_validator.assert_not_awaited()


def test_local_reauth_preserves_transport_and_checks_hub_identity(monkeypatch):
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    entry = FakeConfigEntry(data=local_input() | {"connection_type": "local"})
    flow._reauth_entry = entry
    flow.hass = object()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_mismatch = Mock()
    flow.async_update_and_abort = Mock(return_value={"reason": "reauth_successful"})
    validator = AsyncMock(return_value={"title": "Local Hub", "unique_id": "local-HUB1"})
    monkeypatch.setattr(config_flow_module, "validate_local_input", validator)
    cloud_validator = AsyncMock(side_effect=AssertionError("unexpected cloud validation"))
    monkeypatch.setattr(config_flow_module, "validate_input", cloud_validator)

    result = asyncio.run(flow.async_step_reauth_confirm(local_input()))

    assert result["reason"] == "reauth_successful"
    flow.async_set_unique_id.assert_awaited_once_with("local-HUB1")
    flow._abort_if_unique_id_mismatch.assert_called_once()
    flow.async_update_and_abort.assert_called_once_with(
        entry, data_updates=local_input() | {"connection_type": "local", "name": "Local Hub"}
    )
    cloud_validator.assert_not_awaited()


class FakeConfigEntry:
    def __init__(self, data=None, options=None, entry_id="entry-1"):
        self.data = data or {}
        self.options = options or {}
        self.entry_id = entry_id


class FakeClient:
    def __init__(
        self,
        login_response=None,
        devices_response=None,
        remote_list=None,
        brands=None,
        remote_idxs=None,
        resolved_ai=None,
    ):
        self.login_response = login_response or {"code": "success"}
        self.devices_response = devices_response or []
        self.remote_list = remote_list or {}
        self.brands = brands if brands is not None else {}
        self.remote_idxs = remote_idxs if remote_idxs is not None else []
        self.resolved_ai = resolved_ai
        self.login_calls = 0
        self.device_calls = 0
        self.remote_list_calls = 0
        self.brand_calls = 0
        self.remote_idx_calls = 0
        self.resolve_calls = []

    async def login_async(self):
        self.login_calls += 1
        return self.login_response

    async def get_all_device_async(self):
        self.device_calls += 1
        return self.devices_response

    async def get_ir_remote_list_async(self, hub_id):
        self.remote_list_calls += 1
        return self.remote_list

    async def get_brands_async(self, category):
        self.brand_calls += 1
        return self.brands

    async def get_remote_idxs_async(self, category, brand):
        self.remote_idx_calls += 1
        return self.remote_idxs

    async def resolve_ir_remote_ai_async(self, hub_id, device_id, category, brand, idx):
        self.resolve_calls.append((hub_id, device_id, category, brand, idx))
        return self.resolved_ai


def make_user_input():
    return {
        config_flow_module.CONF_LIFESMART_APPKEY: "appkey",
        config_flow_module.CONF_LIFESMART_APPTOKEN: "apptoken",
        config_flow_module.CONF_LIFESMART_USERID: "userid",
        config_flow_module.CONF_LIFESMART_USERPASSWORD: "password",
        config_flow_module.CONF_REGION: "country:us",
    }


def make_options_flow(entry=None):
    flow = config_flow_module.LifeSmartOptionsFlowHandler(
        entry
        or FakeConfigEntry(
            data=make_user_input(),
            options={},
        )
    )
    flow.hass = type("Hass", (), {"data": {config_flow_module.DOMAIN: {flow._config_entry.entry_id: {"devices": []}}}})()
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}
    flow.async_create_entry = lambda title, data: {"type": "create_entry", "title": title, "data": data}
    flow.async_show_menu = lambda **kwargs: {"type": "menu", **kwargs}
    flow.async_abort = lambda **kwargs: {"type": "abort", **kwargs}
    return flow


def test_validate_input_success_and_failures(monkeypatch):
    fake_client = FakeClient(
        login_response={"code": "success"},
        devices_response=[{"agt": "HUB1"}],
    )
    client_args = []

    def fake_client_factory(*args):
        client_args.append(args)
        return fake_client

    monkeypatch.setattr(config_flow_module, "LifeSmartClient", fake_client_factory)

    result = asyncio.run(config_flow_module.validate_input(object(), make_user_input()))

    assert result == {"title": "User Id userid", "unique_id": "appkey"}
    assert client_args[0][0] == "us"
    assert fake_client.login_calls == 1
    assert fake_client.device_calls == 1

    bad_login_client = FakeClient(login_response={"code": "failure"})
    monkeypatch.setattr(config_flow_module, "LifeSmartClient", lambda *args: bad_login_client)
    with pytest.raises(config_flow_module.LifeSmartInvalidAuth):
        asyncio.run(config_flow_module.validate_input(object(), make_user_input()))

    bad_device_client = FakeClient(login_response={"code": "success"}, devices_response={"code": 500})
    monkeypatch.setattr(config_flow_module, "LifeSmartClient", lambda *args: bad_device_client)
    with pytest.raises(config_flow_module.LifeSmartCannotConnect):
        asyncio.run(config_flow_module.validate_input(object(), make_user_input()))


def test_get_unique_id_and_config_flow_options_factory():
    assert config_flow_module.get_unique_id("abc") == "lifesmart-abc"
    entry = FakeConfigEntry()
    options_flow = config_flow_module.LifeSmartConfigFlowHandler.async_get_options_flow(entry)
    assert isinstance(options_flow, config_flow_module.LifeSmartOptionsFlowHandler)


def test_config_flow_async_step_user_success_and_error(monkeypatch):
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.hass = object()
    unique_ids = []
    aborted = []

    async def fake_set_unique_id(unique_id):
        unique_ids.append(unique_id)

    flow.async_set_unique_id = fake_set_unique_id
    flow._abort_if_unique_id_configured = lambda: aborted.append(True)
    flow.async_create_entry = lambda title, data: {"type": "create_entry", "title": title, "data": data}
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}

    async def fake_validate_input(hass, data):
        return {"title": "User Id userid", "unique_id": "appkey"}

    monkeypatch.setattr(config_flow_module, "validate_input", fake_validate_input)
    user_input = make_user_input()
    result = asyncio.run(flow.async_step_user(user_input))

    assert result["type"] == "create_entry"
    assert result["title"] == "User Id userid"
    assert result["data"][config_flow_module.CONF_NAME] == "User Id userid"
    assert unique_ids == ["appkey"]
    assert aborted == [True]

    async def bad_validate_input(hass, data):
        raise Exception("boom")

    monkeypatch.setattr(config_flow_module, "validate_input", bad_validate_input)
    error_result = asyncio.run(flow.async_step_user(make_user_input()))
    empty_result = asyncio.run(flow.async_step_user())

    assert error_result["type"] == "form"
    assert error_result["errors"]["base"] == "unknown"
    assert empty_result["type"] == "menu"
    assert empty_result["step_id"] == "user"
    assert empty_result["menu_options"] == ["local", "cloud"]


def test_local_config_flow_validates_hub_and_stores_local_settings(monkeypatch):
    instances = []

    class FakeLocalClient:
        def __init__(self, host, port, password):
            self.args = (host, port, password)
            self.closed = False
            self.hub_id = "HUB1"
            instances.append(self)

        async def login_async(self):
            return {"code": "success"}

        async def get_all_device_async(self):
            return [{"agt": "HUB1"}]

        async def async_close(self):
            self.closed = True

    monkeypatch.setattr(config_flow_module, "LocalLifeSmartClient", FakeLocalClient)
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.hass = object()
    unique_ids = []

    async def set_unique_id(unique_id):
        unique_ids.append(unique_id)

    flow.async_set_unique_id = set_unique_id
    flow._abort_if_unique_id_configured = lambda: None
    flow.async_create_entry = lambda title, data: {
        "type": "create_entry",
        "title": title,
        "data": data,
    }

    user_input = {
        config_flow_module.CONF_HOST: "192.168.1.20",
        config_flow_module.CONF_PORT: 8888,
        config_flow_module.CONF_LOCAL_PASSWORD: "admin",
    }
    result = asyncio.run(flow.async_step_local(user_input))

    assert result["title"] == "LifeSmart Hub 192.168.1.20"
    assert result["data"][config_flow_module.CONF_CONNECTION_TYPE] == "local"
    assert unique_ids == ["local-HUB1"]
    assert instances[0].args == ("192.168.1.20", 8888, "admin")
    assert instances[0].closed is True


def test_local_config_flow_discovers_hub_and_uses_advertised_port(monkeypatch):
    discovered_hub = config_flow_module.DiscoveredLifeSmartHub(
        host="192.168.1.115",
        hub_id="hub_id",
        port=9876,
        model="LSJZX1K",
    )

    async def fake_discover(timeout):
        assert timeout == config_flow_module.DEFAULT_DISCOVERY_TIMEOUT
        return [discovered_hub]

    validated_inputs = []

    async def fake_validate(hass, data):
        validated_inputs.append(dict(data))
        return {"title": "LifeSmart Hub 192.168.1.115", "unique_id": "local-hub"}

    monkeypatch.setattr(config_flow_module, "async_discover_local_hubs", fake_discover)
    monkeypatch.setattr(config_flow_module, "validate_local_input", fake_validate)
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.hass = object()
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}
    flow.async_set_unique_id = lambda unique_id: asyncio.sleep(0)
    flow._abort_if_unique_id_configured = lambda: None
    flow.async_create_entry = lambda title, data: {
        "type": "create_entry",
        "title": title,
        "data": data,
    }

    form = asyncio.run(flow.async_step_local())
    defaults = form["data_schema"](
        {config_flow_module.CONF_LOCAL_PASSWORD: "secret"}
    )
    result = asyncio.run(
        flow.async_step_local(
            {
                config_flow_module.CONF_HOST: "192.168.1.115",
                config_flow_module.CONF_LOCAL_PASSWORD: "secret",
            }
        )
    )

    assert defaults[config_flow_module.CONF_HOST] == "192.168.1.115"
    assert defaults[config_flow_module.CONF_PORT] == 9876
    assert validated_inputs[0][config_flow_module.CONF_PORT] == 9876
    assert result["type"] == "create_entry"


def test_local_config_flow_falls_back_to_manual_schema(monkeypatch):
    async def fake_discover(timeout):
        return []

    monkeypatch.setattr(config_flow_module, "async_discover_local_hubs", fake_discover)
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.hass = object()
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}

    form = asyncio.run(flow.async_step_local())
    values = form["data_schema"](
        {
            config_flow_module.CONF_HOST: "192.168.1.115",
            config_flow_module.CONF_LOCAL_PASSWORD: "secret",
        }
    )

    assert values[config_flow_module.CONF_PORT] == 8888


def test_local_config_flow_maps_bad_password_to_invalid_auth(monkeypatch):
    class FakeLocalClient:
        def __init__(self, *args):
            pass

        async def login_async(self):
            return {"code": "failure"}

        async def async_close(self):
            return None

    monkeypatch.setattr(config_flow_module, "LocalLifeSmartClient", FakeLocalClient)
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.hass = object()
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}
    result = asyncio.run(
        flow.async_step_local(
            {
                config_flow_module.CONF_HOST: "192.168.1.20",
                config_flow_module.CONF_PORT: 8888,
                config_flow_module.CONF_LOCAL_PASSWORD: "wrong",
            }
        )
    )

    assert result["errors"] == {"base": "invalid_auth"}


def test_local_schema_defaults_to_port_8888_and_admin_password():
    validated = config_flow_module.vol.Schema(config_flow_module.LOCAL_DATA_SCHEMA)(
        {config_flow_module.CONF_HOST: "192.168.1.20"}
    )

    assert validated[config_flow_module.CONF_PORT] == 8888
    assert validated[config_flow_module.CONF_LOCAL_PASSWORD] == "admin"


def test_config_flow_maps_connection_and_auth_errors(monkeypatch):
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.hass = object()
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}

    async def invalid_auth(hass, data):
        raise config_flow_module.LifeSmartInvalidAuth

    monkeypatch.setattr(config_flow_module, "validate_input", invalid_auth)
    result = asyncio.run(flow.async_step_user(make_user_input()))
    assert result["errors"] == {"base": "invalid_auth"}

    async def cannot_connect(hass, data):
        raise config_flow_module.LifeSmartCannotConnect

    monkeypatch.setattr(config_flow_module, "validate_input", cannot_connect)
    result = asyncio.run(flow.async_step_user(make_user_input()))
    assert result["errors"] == {"base": "cannot_connect"}


def test_reauth_updates_existing_entry(monkeypatch):
    entry = FakeConfigEntry(data=make_user_input())
    flow = config_flow_module.LifeSmartConfigFlowHandler()
    flow.context = {"entry_id": entry.entry_id}
    flow.hass = type(
        "Hass",
        (),
        {"config_entries": type("Entries", (), {"async_get_entry": lambda self, entry_id: entry})()},
    )()
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}
    flow.async_set_unique_id = lambda unique_id: asyncio.sleep(0)
    flow._abort_if_unique_id_mismatch = lambda: None
    flow.async_update_and_abort = lambda config_entry, **kwargs: {
        "type": "abort",
        "reason": "reauth_successful",
        **kwargs,
    }

    form = asyncio.run(flow.async_step_reauth(entry.data))
    assert form["step_id"] == "reauth_confirm"

    async def valid_input(hass, data):
        return {"title": "User Id userid", "unique_id": "appkey"}

    monkeypatch.setattr(config_flow_module, "validate_input", valid_input)
    updated = make_user_input() | {config_flow_module.CONF_LIFESMART_USERPASSWORD: "new"}
    result = asyncio.run(flow.async_step_reauth_confirm(updated))
    assert result["reason"] == "reauth_successful"
    assert result["data_updates"] == updated


def test_options_flow_client_helpers_and_normalizers(monkeypatch):
    entry = FakeConfigEntry(
        data=make_user_input(),
        options={config_flow_module.CONF_LIFESMART_APPKEY: "opt-appkey"},
    )
    flow = make_options_flow(entry)
    fake_client = FakeClient()
    client_args = []

    def fake_client_factory(*args):
        client_args.append(args)
        return fake_client

    monkeypatch.setattr(config_flow_module, "LifeSmartClient", fake_client_factory)

    client = asyncio.run(flow._get_client())
    cached_client = asyncio.run(flow._get_client())

    assert client is fake_client
    assert cached_client is fake_client
    assert fake_client.login_calls == 1
    assert client_args[0][0] == "us"
    assert flow._get_entry_value(config_flow_module.CONF_LIFESMART_APPKEY) == "opt-appkey"
    assert config_flow_module.normalize_lifesmart_region("country:th") == "apz"
    assert config_flow_module.normalize_lifesmart_region("EUR") == "eur"
    assert flow._normalize_brand_options({"aux": {"name": "Aux"}, "midea": "Midea"}) == {
        "aux": "Aux",
        "midea": "Midea",
    }
    assert flow._normalize_brand_options([{"brand": "aux", "name": "Aux"}, "midea"]) == {
        "aux": "Aux",
        "midea": "midea",
    }
    assert flow._normalize_brand_options(None) == {}
    assert flow._normalize_remote_idx_options([{"idx": "1"}, "2"]) == ["1", "2"]
    assert flow._normalize_remote_idx_options({"a": "1", "b": "2"}) == ["1", "2"]
    assert flow._normalize_remote_idx_options(None) == []


def test_options_flow_spot_devices_and_remote_defaults(monkeypatch):
    entry = FakeConfigEntry(data=make_user_input())
    flow = make_options_flow(entry)
    flow.hass.data[config_flow_module.DOMAIN][entry.entry_id]["devices"] = [
        {
            config_flow_module.HUB_ID_KEY: "HUB1",
            config_flow_module.DEVICE_ID_KEY: "SPOT1",
            config_flow_module.DEVICE_TYPE_KEY: config_flow_module.SPOT_TYPES[0],
            config_flow_module.DEVICE_NAME_KEY: "Spot",
        },
        {
            config_flow_module.HUB_ID_KEY: "HUB1",
            config_flow_module.DEVICE_ID_KEY: "OTHER1",
            config_flow_module.DEVICE_TYPE_KEY: "SL_OL",
            config_flow_module.DEVICE_NAME_KEY: "Other",
        },
    ]
    fake_client = FakeClient(
        remote_list={
            "bad": "ignore",
            "prefix-SPOT1-remote": {
                "category": config_flow_module.IR_CATEGORY_AC,
                "brand": "aux",
                "idx": "33.irxs",
            }
        }
    )
    monkeypatch.setattr(config_flow_module, "LifeSmartClient", lambda *args: fake_client)

    assert flow._get_spot_devices() == [flow.hass.data[config_flow_module.DOMAIN][entry.entry_id]["devices"][0]]
    default = asyncio.run(flow._get_device_remote_default("HUB1_SPOT1"))
    cached = asyncio.run(flow._get_device_remote_default("HUB1_SPOT1"))

    assert default == {
        "category": config_flow_module.IR_CATEGORY_AC,
        "brand": "aux",
        "idx": "33.irxs",
        "ai": "prefix-SPOT1-remote",
    }
    assert cached == default
    assert fake_client.remote_list_calls == 1

    error_client = FakeClient()
    async def raise_remote_list(hub_id):
        raise RuntimeError("fail")
    error_client.get_ir_remote_list_async = raise_remote_list
    flow._client = error_client
    assert asyncio.run(flow._get_device_remote_default("HUB2_SPOT2")) == {}


def test_options_flow_init_and_ac_device_steps(monkeypatch):
    flow = make_options_flow(
        FakeConfigEntry(
            data=make_user_input(),
            options={config_flow_module.CONF_AC_CONFIG: {"HUB1_SPOT1": {"brand": "aux"}}},
        )
    )
    init_result = asyncio.run(flow.async_step_init())
    assert init_result["type"] == "menu"
    assert "ac_remove" in init_result["menu_options"]

    local_flow = make_options_flow(
        FakeConfigEntry(
            data={
                config_flow_module.CONF_CONNECTION_TYPE: "local",
                config_flow_module.CONF_HOST: "192.168.1.20",
                config_flow_module.CONF_PORT: 8888,
                config_flow_module.CONF_LOCAL_PASSWORD: "admin",
            }
        )
    )
    assert asyncio.run(local_flow.async_step_init())["menu_options"] == ["user"]

    no_spot_flow = make_options_flow()
    assert asyncio.run(no_spot_flow.async_step_ac_device()) == {"type": "abort", "reason": "no_spot_devices"}

    spot_device = {
        config_flow_module.HUB_ID_KEY: "HUB1",
        config_flow_module.DEVICE_ID_KEY: "SPOT1",
        config_flow_module.DEVICE_TYPE_KEY: config_flow_module.SPOT_TYPES[0],
        config_flow_module.DEVICE_NAME_KEY: "Spot",
    }
    flow.hass.data[config_flow_module.DOMAIN][flow._config_entry.entry_id]["devices"] = [spot_device]

    async def fake_default(device_key):
        return {"category": config_flow_module.IR_CATEGORY_AC, "brand": "aux", "idx": "33.irxs", "ai": "AI1"}

    flow._get_device_remote_default = fake_default
    result = asyncio.run(flow.async_step_ac_device({"device": "HUB1_SPOT1"}))
    assert result["type"] == "create_entry"
    assert result["data"][config_flow_module.CONF_AC_CONFIG]["HUB1_SPOT1"]["brand"] == "aux"

    async def bad_default(device_key):
        return {}

    flow._get_device_remote_default = bad_default
    error_result = asyncio.run(flow.async_step_ac_device({"device": "HUB1_SPOT1"}))
    form_result = asyncio.run(flow.async_step_ac_device())

    assert error_result["type"] == "form"
    assert error_result["errors"]["base"] == "no_ac_remote_assigned"
    assert form_result["type"] == "form"


def test_options_flow_ac_brand_remote_and_remove_steps():
    entry = FakeConfigEntry(
        data=make_user_input(),
        options={config_flow_module.CONF_AC_CONFIG: {"HUB1_SPOT1": {"brand": "aux", "idx": "33.irxs"}}},
    )
    flow = make_options_flow(entry)
    flow.hass.data[config_flow_module.DOMAIN][entry.entry_id]["devices"] = [
        {
            config_flow_module.HUB_ID_KEY: "HUB1",
            config_flow_module.DEVICE_ID_KEY: "SPOT1",
            config_flow_module.DEVICE_TYPE_KEY: config_flow_module.SPOT_TYPES[0],
            config_flow_module.DEVICE_NAME_KEY: "Spot",
        }
    ]
    flow._selected_device_key = "HUB1_SPOT1"
    flow._client = FakeClient(
        brands={"aux": {"name": "Aux"}},
        remote_idxs=["33.irxs", "44.irxs"],
        resolved_ai="AI-REMOTE",
    )
    flow._get_device_remote_default = lambda device_key: asyncio.sleep(0, result={"category": config_flow_module.IR_CATEGORY_AC, "brand": "aux", "idx": "33.irxs", "ai": "AI1"})

    brand_form = asyncio.run(flow.async_step_ac_brand())
    brand_result = asyncio.run(flow.async_step_ac_brand({"brand": "aux"}))

    assert brand_form["type"] == "form"
    assert brand_result["type"] == "form"
    assert brand_result["step_id"] == "ac_remote"

    remote_form = asyncio.run(flow.async_step_ac_remote())
    remote_result = asyncio.run(flow.async_step_ac_remote({"idx": "44.irxs"}))

    assert remote_form["type"] == "form"
    assert remote_result["type"] == "create_entry"
    assert remote_result["data"][config_flow_module.CONF_AC_CONFIG]["HUB1_SPOT1"] == {
        "category": config_flow_module.IR_CATEGORY_AC,
        "brand": "aux",
        "idx": "44.irxs",
        "ai": "AI-REMOTE",
    }

    remove_form = asyncio.run(flow.async_step_ac_remove())
    remove_result = asyncio.run(flow.async_step_ac_remove({"device": "HUB1_SPOT1"}))
    empty_remove_flow = make_options_flow(FakeConfigEntry(data=make_user_input(), options={}))

    assert remove_form["type"] == "form"
    assert remove_result == {"type": "create_entry", "title": "", "data": {}}
    assert asyncio.run(empty_remove_flow.async_step_ac_remove()) == {
        "type": "abort",
        "reason": "no_ac_config",
    }


def test_options_flow_handles_brand_and_remote_errors():
    flow = make_options_flow()
    flow._selected_device_key = "HUB1_SPOT1"
    flow._selected_brand = "aux"
    flow._client = FakeClient()
    async def bad_brands(category):
        raise RuntimeError("brand-fail")
    async def bad_remote_idxs(category, brand):
        raise RuntimeError("idx-fail")
    flow._client.get_brands_async = bad_brands
    flow._client.get_remote_idxs_async = bad_remote_idxs
    flow._get_device_remote_default = lambda device_key: asyncio.sleep(0, result={})

    brand_form = asyncio.run(flow.async_step_ac_brand())
    remote_form = asyncio.run(flow.async_step_ac_remote())

    assert brand_form["type"] == "form"
    assert brand_form["errors"]["base"] == "brand-fail"
    assert remote_form["type"] == "form"
    assert remote_form["errors"]["base"] == "idx-fail"
