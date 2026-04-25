import asyncio
import importlib

switch_module = importlib.import_module("custom_components.lifesmart.switch")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(self, entry_id, devices, exclude_devices=None, exclude_hubs=None, client=None):
        self.data = {
            switch_module.DOMAIN: {
                entry_id: {
                    "devices": devices,
                    "exclude_devices": exclude_devices or [],
                    "exclude_hubs": exclude_hubs or [],
                    "client": client,
                }
            }
        }


class FakeClient:
    def __init__(self, on_results=None, off_results=None):
        self.on_results = list(on_results or [])
        self.off_results = list(off_results or [])
        self.on_calls = []
        self.off_calls = []

    async def turn_on_light_swith_async(self, idx, hub_id, device_id):
        self.on_calls.append((idx, hub_id, device_id))
        return self.on_results.pop(0) if self.on_results else 0

    async def turn_off_light_swith_async(self, idx, hub_id, device_id):
        self.off_calls.append((idx, hub_id, device_id))
        return self.off_results.pop(0) if self.off_results else 0


class FakeSceneClient(FakeClient):
    async def set_scene_async(self, agt, scene_id):
        return {"code": 0}


def make_device(device_type, data, device_id="DEV1", hub_id="HUB1"):
    return {
        "name": "Switch Device",
        "devtype": device_type,
        "agt": hub_id,
        "me": device_id,
        "ver": "1.0",
        "data": data,
    }


def make_switch_entity(device_type="SL_OL", sub_device_key="P1", sub_device_data=None, client=None):
    raw = make_device(device_type, {sub_device_key: sub_device_data or {"type": 1, "val": 1}})
    entity = switch_module.LifeSmartSwitch(None, raw, sub_device_key, raw["data"][sub_device_key], client or FakeClient())
    updates = []
    entity.schedule_update_ha_state = lambda: updates.append("scheduled")
    entity.async_schedule_update_ha_state = lambda: updates.append("async")
    return entity, updates


def test_async_setup_entry_creates_supported_switch_entities(monkeypatch):
    monkeypatch.setattr(switch_module, "is_nature_switch", lambda device: True)
    devices = [
        make_device("SL_OL", {"P1": {"type": 1, "val": 1}}),
        make_device("OD_MFRESH_M8088", {"O": {"type": 1, "val": 1}}, device_id="AIR1"),
        make_device("SL_JEMA", {"P8": {"type": 1, "val": 1}, "P6": {"type": 1, "val": 1}}, device_id="CTRL1"),
        make_device("V_485_P", {"O": {"type": 1, "val": 1}, "L1": {"type": 1, "val": 1}}, device_id="MOD1"),
        make_device("SL_OE_DE", {"P1": {"type": 1, "val": 1}}, device_id="PLUG1"),
        make_device("SL_NATURE", {"P1": {"type": 1, "val": 1}, "P2": {"type": 0, "val": 0}}, device_id="NAT1"),
        make_device("SL_SPOT", {"P1": {"type": 1, "val": 1}}, device_id="SKIP"),
        make_device("SL_OL", {"P1": {"type": 1, "val": 1}}, device_id="EXCLUDED"),
    ]
    hass = FakeHass("entry-1", devices, exclude_devices=["EXCLUDED"], client=FakeClient())
    added = []

    asyncio.run(switch_module.async_setup_entry(hass, FakeConfigEntry(), lambda entities: added.extend(entities)))

    assert len(added) == 8
    assert any(entity.entity_id == "switch.sl_ol_hub1_dev1_p1" for entity in added)
    assert any(entity.entity_id == "switch.od_mfresh_m8088_hub1_air1_o" for entity in added)
    assert any(entity.entity_id == "switch.sl_jema_hub1_ctrl1_p8" for entity in added)
    assert any(entity.entity_id == "switch.v_485_p_hub1_mod1_l1" for entity in added)
    assert any(entity.entity_id == "switch.sl_oe_de_hub1_plug1_p1" for entity in added)
    assert any(entity.entity_id == "switch.sl_nature_hub1_nat1_p1" for entity in added)


def test_switch_entity_properties_updates_and_turn_on_off():
    client = FakeClient(on_results=[0, 1], off_results=[0, 1])
    entity, updates = make_switch_entity(client=client)

    assert entity.name == ""
    assert entity.is_on is True
    assert entity.unique_id == entity.entity_id
    assert entity.device_info["model"] == "SL_OL"

    asyncio.run(entity._update_state({"type": 0}))
    asyncio.run(entity._update_state(None))
    asyncio.run(entity.async_turn_on())
    asyncio.run(entity.async_turn_on())
    asyncio.run(entity.async_turn_off())
    asyncio.run(entity.async_turn_off())

    assert entity._get_state() is False
    assert client.on_calls == [("P1", "HUB1", "DEV1"), ("P1", "HUB1", "DEV1")]
    assert client.off_calls == [("P1", "HUB1", "DEV1"), ("P1", "HUB1", "DEV1")]
    assert updates == ["scheduled", "async", "async"]


def test_switch_async_added_to_hass_registers_dispatcher(monkeypatch):
    entity, _updates = make_switch_entity()
    entity.hass = object()
    removers = []
    calls = []

    def fake_connect(hass, signal, callback):
        calls.append((hass, signal, callback))
        return "remove-token"

    entity.async_on_remove = lambda remover: removers.append(remover)
    monkeypatch.setattr(switch_module, "async_dispatcher_connect", fake_connect)

    asyncio.run(entity.async_added_to_hass())

    assert calls[0][1] == f"{switch_module.LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity.entity_id}"
    assert removers == ["remove-token"]


def test_scene_switch_turns_on_and_off(monkeypatch):
    raw = make_device("ai", {})
    scene = switch_module.LifeSmartSceneSwitch(None, raw, FakeSceneClient())
    updates = []
    scene.async_schedule_update_ha_state = lambda: updates.append("scheduled")

    async def fake_scene_set(*args):
        return 0

    monkeypatch.setattr(switch_module.LifeSmartDevice, "async_lifesmart_sceneset", fake_scene_set)

    asyncio.run(scene.async_turn_on())
    asyncio.run(scene.async_turn_off())

    assert scene.device_info["model"] == "ai"
    assert scene.unique_id == scene.entity_id
    assert scene._get_state() is False
    assert updates == ["scheduled", "scheduled"]
