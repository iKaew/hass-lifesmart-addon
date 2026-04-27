import asyncio
import importlib

import pytest

config_flow_module = importlib.import_module("custom_components.lifesmart.config_flow")


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
    with pytest.raises(Exception, match="Error connecting to LifeSmart API"):
        asyncio.run(config_flow_module.validate_input(object(), make_user_input()))

    bad_device_client = FakeClient(login_response={"code": "success"}, devices_response={"code": 500})
    monkeypatch.setattr(config_flow_module, "LifeSmartClient", lambda *args: bad_device_client)
    with pytest.raises(Exception, match="Error connecting to LifeSmart API"):
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
    assert error_result["errors"]["base"] == "boom"
    assert empty_result["type"] == "form"
    assert empty_result["step_id"] == "user"


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
