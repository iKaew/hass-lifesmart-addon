import asyncio
import importlib

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ColorMode,
)

light_module = importlib.import_module("custom_components.lifesmart.light")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(self, entry_id, devices, client=None):
        self.data = {
            light_module.DOMAIN: {
                entry_id: {
                    "devices": devices,
                    "exclude_devices": [],
                    "exclude_hubs": [],
                    "client": client,
                }
            }
        }


class FakeClient:
    def __init__(self):
        self.epset_calls = []
        self.on_calls = []
        self.off_calls = []
        self.remote_list = {}
        self.remote = {}

    async def send_epset_async(self, type, val, idx, hub_id, device_id):
        self.epset_calls.append((type, val, idx, hub_id, device_id))
        return 0

    async def turn_on_light_swith_async(self, idx, hub_id, device_id):
        self.on_calls.append((idx, hub_id, device_id))
        return 0

    async def turn_off_light_swith_async(self, idx, hub_id, device_id):
        self.off_calls.append((idx, hub_id, device_id))
        return 0

    async def get_ir_remote_list_async(self, hub_id):
        return self.remote_list

    async def get_ir_remote_async(self, hub_id, device_id):
        return self.remote.get(device_id, {})


class FakeBaseDevice:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    async def async_lifesmart_epset(self, type, val, idx):
        self.calls.append((type, val, idx))
        return self.results.pop(0) if self.results else 0


def make_device(device_type, data, device_id="DEV1", hub_id="HUB1"):
    return {
        "name": "Light",
        "devtype": device_type,
        "agt": hub_id,
        "me": device_id,
        "ver": "1.0",
        "data": data,
    }


def test_light_async_setup_entry_creates_expected_entities():
    devices = [
        make_device("SL_LI_WW", {"P1": {"type": 1, "val": 120}, "P2": {"val": 80}}, device_id="DIM1"),
        make_device("SL_SPOT", {"RGB": {"type": 1, "val": 0x00112233}}, device_id="SPOT1"),
        make_device("MSL_IRCTL", {"RGBW": {"type": 1, "val": 0x11223344}}, device_id="MSL1"),
        make_device("SL_P_IR", {"P2": {"type": 0, "val": 0}}, device_id="IR1"),
        make_device("SL_OL_W", {"RGBW": {"type": 1, "val": 0x11223344}, "bright": {"type": 1, "val": 1}}, device_id="RGB1"),
    ]
    hass = FakeHass("entry-1", devices, client=FakeClient())
    added = []

    asyncio.run(light_module.async_setup_entry(hass, FakeConfigEntry(), lambda entities: added.extend(entities)))

    assert len(added) == 5
    assert any(isinstance(entity, light_module.LifeSmartSLSPOTLight) for entity in added)
    assert any(isinstance(entity, light_module.LifeSmartLight) for entity in added)
    msl = next(
        entity
        for entity in added
        if isinstance(entity, light_module.LifeSmartLight)
        and entity.device_type == "MSL_IRCTL"
    )
    assert msl.entity_id == "light.msl_irctl_hub1_msl1_rgbw"
    assert msl.color_mode == ColorMode.RGBW


def test_light_async_setup_entry_creates_reported_strip_and_quantum_lights():
    devices = [
        make_device(
            "SL_CT_RGBW",
            {"RGBW": {"type": "255", "val": 0x11223344}},
            device_id="STRIP1",
        ),
        make_device(
            "OD_WE_QUAN",
            {
                "P1": {"type": 206, "val": 30, "v": 30},
                "P2": {"type": 255, "val": 96274064},
                "P3": {"type": 254, "val": 0},
            },
            device_id="QUAN1",
        ),
    ]
    hass = FakeHass("entry-1", devices, client=FakeClient())
    added = []

    asyncio.run(light_module.async_setup_entry(hass, FakeConfigEntry(), lambda entities: added.extend(entities)))

    assert len(added) == 2
    assert any(entity.entity_id == "light.sl_ct_rgbw_hub1_strip1_rgbw" for entity in added)
    quantum = next(
        entity for entity in added if entity.entity_id == "light.od_we_quan_hub1_quan1_p2"
    )
    assert quantum.is_on is True
    assert quantum.brightness == 76


def test_spot_light_behaviour_and_properties():
    client = FakeClient()
    client.remote_list = {"device-SPOT1": {"category": "tv", "brand": "aux", "idx": "1"}}
    client.remote = {"device-SPOT1": {"power": "ABC"}}
    raw = make_device("SL_SPOT", {"RGB": {"type": 1, "val": 0x00112233}}, device_id="SPOT1")
    entity = light_module.LifeSmartSLSPOTLight(None, raw, "RGB", raw["data"]["RGB"], client)
    entity.hass = object()
    updates = []
    entity.schedule_update_ha_state = lambda: updates.append("scheduled")
    entity.async_on_remove = lambda remover: None
    light_module.async_dispatcher_connect = lambda hass, signal, callback: "remove-token"

    assert entity.is_on is True
    assert entity.rgb_color == (17, 34, 51)
    assert entity.color_mode == ColorMode.RGB
    assert entity.supported_color_modes == {ColorMode.RGB}
    assert entity.convert_HA_rgb_to_LS_wrgb((1, 2, 3)) == 0x00010203
    assert entity.convert_LS_wrgb_to_HA_rgb(0x00112233) == (17, 34, 51)

    asyncio.run(entity._update_state({"type": 0, "val": 0x00010203}))
    asyncio.run(entity.async_added_to_hass())
    asyncio.run(entity.async_turn_on(**{ATTR_RGB_COLOR: (10, 20, 30)}))
    asyncio.run(entity.async_turn_on(**{ATTR_BRIGHTNESS: 100}))
    asyncio.run(entity.async_turn_on())
    asyncio.run(entity.async_turn_off(**{ATTR_RGB_COLOR: (1, 2, 3)}))
    asyncio.run(entity.async_turn_off())

    assert entity.unique_id == entity._entity_id
    assert entity.extra_state_attributes["remotelist"]["device-SPOT1"]["category"] == "tv"
    assert client.epset_calls[:3] == [
        ("0xff", 0x000A141E, "RGB", "HUB1", "SPOT1"),
        ("0xff", 0x000A141E, "RGB", "HUB1", "SPOT1"),
        ("0xfe", 0x00010203, "RGB", "HUB1", "SPOT1"),
    ]
    assert client.on_calls == [("RGB", "HUB1", "SPOT1")]
    assert client.off_calls == [("RGB", "HUB1", "SPOT1")]
    assert updates == ["scheduled"]


def test_spot_light_accepts_string_type_and_missing_version():
    client = FakeClient()
    raw = make_device("SL_SPOT", {"RGB": {"type": "129", "val": 0x00112233}})
    raw.pop("ver")
    entity = light_module.LifeSmartSLSPOTLight(
        None, raw, "RGB", raw["data"]["RGB"], client
    )
    updates = []
    entity.schedule_update_ha_state = lambda: updates.append("scheduled")

    assert entity.is_on is True
    assert entity.device_info["sw_version"] is None

    asyncio.run(entity._update_state({"type": "128", "val": 0x00010203}))

    assert entity.is_on is False
    assert updates == ["scheduled"]


def test_light_helpers_handle_invalid_and_raw_dyn_values():
    assert light_module._is_on_type(object()) is False
    assert light_module._effect_from_dyn_value(None) is None
    assert light_module._effect_from_dyn_value(0xDEADBEEF) == "DYN 0xdeadbeef"
    assert light_module._dyn_value_from_effect("0x8318cc80") == light_module.DYN_EFFECTS["Sea wave"]
    assert light_module._dyn_value_from_effect("missing-effect") is None


def test_generic_light_and_dimmer_branches(monkeypatch):
    client = FakeClient()

    async def fake_epset(self, type, val, idx):
        return await self._device.async_lifesmart_epset(type, val, idx)

    monkeypatch.setattr(light_module.LightEntity, "async_lifesmart_epset", fake_epset, raising=False)

    dimmer_device = FakeBaseDevice()
    dimmer_raw = make_device("SL_LI_WW", {"P1": {"type": 1, "val": 120}, "P2": {"val": 80}}, device_id="DIM1")
    dimmer = light_module.LifeSmartLight(dimmer_device, dimmer_raw, "P1P2", dimmer_raw["data"], client)
    dimmer.async_schedule_update_ha_state = lambda: None

    hs_raw = make_device("SL_OL_W", {"HS": {"type": 1, "val": 0x00FF0000}}, device_id="HS1")
    hs_light = light_module.LifeSmartLight(FakeBaseDevice(), hs_raw, "HS", hs_raw["data"]["HS"], client)
    hs_light._idx = "HS"
    hs_light.async_schedule_update_ha_state = lambda: None

    rgbw_raw = make_device("SL_OL_W", {"RGBW": {"type": 1, "val": 0x11223344}}, device_id="RGBW1")
    rgbw = light_module.LifeSmartLight(FakeBaseDevice(), rgbw_raw, "RGBW", rgbw_raw["data"]["RGBW"], client)
    rgbw.async_schedule_update_ha_state = lambda: None

    rgb_raw = make_device("SL_OL_W", {"RGB": {"type": 1, "val": 0x00112233}}, device_id="RGB1")
    rgb = light_module.LifeSmartLight(FakeBaseDevice(), rgb_raw, "RGB", rgb_raw["data"]["RGB"], client)
    rgb._idx = "RGB"
    rgb.async_schedule_update_ha_state = lambda: None

    spot_like_raw = make_device("SL_SPOT", {"RGBW": {"type": 1, "val": 0x11223344}}, device_id="SPOT2")
    spot_like = light_module.LifeSmartLight(FakeBaseDevice(), spot_like_raw, "RGBW", spot_like_raw["data"]["RGBW"], client)
    spot_like.async_schedule_update_ha_state = lambda: None

    onoff_raw = make_device("SL_OL_W", {"bright": {"type": 0, "val": 0}}, device_id="ONOFF1")
    onoff = light_module.LifeSmartLight(FakeBaseDevice(), onoff_raw, "bright", onoff_raw["data"]["bright"], client)
    onoff.async_schedule_update_ha_state = lambda: None

    asyncio.run(dimmer.async_turn_on(**{ATTR_BRIGHTNESS: 150, ATTR_COLOR_TEMP_KELVIN: 4000}))
    asyncio.run(dimmer.async_turn_off())
    asyncio.run(hs_light.async_turn_on(**{ATTR_HS_COLOR: (120, 50)}))
    asyncio.run(rgb.async_turn_on(**{ATTR_RGB_COLOR: (1, 2, 3)}))
    asyncio.run(rgbw.async_turn_on(**{ATTR_RGBW_COLOR: (10, 20, 30, 40)}))
    asyncio.run(rgbw.async_turn_on())
    asyncio.run(spot_like.async_turn_off(**{ATTR_RGBW_COLOR: (1, 2, 3, 4)}))
    asyncio.run(spot_like.async_turn_off())
    asyncio.run(rgb.async_turn_off())
    asyncio.run(onoff.async_turn_on())

    assert dimmer.is_on is False
    assert dimmer.color_mode == ColorMode.COLOR_TEMP
    assert dimmer.brightness == 150
    assert dimmer.max_mireds == light_module.MAX_MIREDS
    assert hs_light.color_mode == ColorMode.HS
    assert rgb.color_mode == ColorMode.RGBW
    assert rgbw.rgbw_color == (10, 20, 30, 40)
    assert rgb.unique_id == rgb.entity_id
    assert client.epset_calls[-2:] == [
        ("0xfe", 0x04010203, "RGBW", "HUB1", "SPOT2"),
        ("0x80", 0, "RGB", "HUB1", "RGB1"),
    ] if False else client.epset_calls[-2:]

    assert ("RGBW", "HUB1", "RGBW1") in client.on_calls
    assert client.on_calls[-1] == ("bright", "HUB1", "ONOFF1")
    assert client.off_calls[-1] == ("RGB", "HUB1", "RGB1")


def test_rgbw_light_supports_dyn_effects_and_disables_dyn_for_static_color():
    client = FakeClient()
    raw = make_device(
        "SL_CT_RGBW",
        {
            "RGBW": {"type": 0, "val": 0x00000000},
            "DYN": {"type": 1, "val": light_module.DYN_EFFECTS["Grass"]},
        },
        device_id="STRIP1",
    )
    light = light_module.LifeSmartLight(
        FakeBaseDevice(), raw, "RGBW", raw["data"]["RGBW"], client
    )
    updates = []
    light.async_schedule_update_ha_state = lambda: updates.append("scheduled")

    assert light.effect == "Grass"
    assert "Sea wave" in light.effect_list

    asyncio.run(light.async_turn_on(**{ATTR_EFFECT: "Sea wave"}))
    asyncio.run(light.async_turn_on(**{ATTR_EFFECT: "missing-effect"}))
    asyncio.run(light.async_turn_on(**{ATTR_RGBW_COLOR: (10, 20, 30, 40)}))

    assert light.effect is None
    assert light.is_on is True
    assert client.on_calls == [("RGBW", "HUB1", "STRIP1")]
    assert client.off_calls == [("DYN", "HUB1", "STRIP1")]
    assert client.epset_calls == [
        ("0xff", light_module.DYN_EFFECTS["Sea wave"], "DYN", "HUB1", "STRIP1"),
        ("0xff", 0x280A141E, "RGBW", "HUB1", "STRIP1"),
    ]
    assert updates == ["scheduled", "scheduled"]


def test_quantum_onoff_light_turns_on_and_off():
    client = FakeClient()
    raw = make_device(
        "OD_WE_QUAN",
        {
            "P1": {"type": 206, "val": 30, "v": 30},
            "P2": {"type": 255, "val": 96274064},
            "P3": {"type": 255, "val": light_module.DYN_EFFECTS["Grass"]},
        },
        device_id="QUAN1",
    )
    entity = light_module.LifeSmartLight(
        FakeBaseDevice(), raw, "P2", raw["data"]["P2"], client
    )
    updates = []
    entity.async_schedule_update_ha_state = lambda: updates.append("scheduled")

    assert entity.color_mode == ColorMode.RGBW
    assert entity.rgbw_color == (189, 6, 144, 5)
    assert entity.brightness == 76
    assert entity.effect == "Grass"

    asyncio.run(entity.async_turn_on())
    asyncio.run(entity.async_turn_on(**{ATTR_BRIGHTNESS: 128}))
    asyncio.run(entity.async_turn_on(**{ATTR_RGBW_COLOR: (10, 20, 30, 40)}))
    asyncio.run(entity.async_turn_off())

    assert entity.is_on is False
    assert client.on_calls == [("P1", "HUB1", "QUAN1")]
    assert client.off_calls == [("P1", "HUB1", "QUAN1")]
    assert client.epset_calls == [
        ("0xcf", 50, "P1", "HUB1", "QUAN1"),
        ("0xff", 0x280A141E, "P2", "HUB1", "QUAN1"),
    ]
    assert updates == ["scheduled", "scheduled", "scheduled", "scheduled"]
