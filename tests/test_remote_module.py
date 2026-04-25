import asyncio
import importlib

remote_module = importlib.import_module("custom_components.lifesmart.remote")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(self, entry_id, devices, client=None):
        self.data = {
            remote_module.DOMAIN: {
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
        self.sent = []

    async def send_ir_code_async(self, hub_id, device_id, ir_code):
        self.sent.append((hub_id, device_id, ir_code))


class FakeStore:
    def __init__(self, data=None):
        self.data = data
        self.saved = []

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data
        self.saved.append(data)


def make_raw_device(device_id="SPOT1"):
    return {
        "name": "Spot",
        "devtype": "SL_SPOT",
        "agt": "HUB1",
        "me": device_id,
        "ver": "1.0",
    }


def test_remote_async_setup_entry_and_helpers():
    devices = [make_raw_device("SPOT1"), {"name": "Other", "devtype": "SL_OL", "agt": "HUB1", "me": "OTHER", "ver": "1.0"}]
    hass = FakeHass("entry-1", devices, client=FakeClient())
    added = []
    asyncio.run(remote_module.async_setup_entry(hass, FakeConfigEntry(), lambda entities: added.extend(entities)))
    assert len(added) == 1
    assert added[0].entity_id == "remote.sl_spot_hub1_spot1_remote"
    assert remote_module._ensure_command_list(None) == []
    assert remote_module._ensure_command_list("power") == ["power"]
    assert remote_module._command_device_key(None) == remote_module.DEFAULT_COMMAND_DEVICE
    assert remote_module._extract_learned_ir_code(["power", "ABC"], "ir") == ("ABC", ["power"])
    assert remote_module._normalize_stored_commands({"tv": {"power": "ABC"}, "orphan": "RAW"}) == {
        "tv": {"power": "ABC"},
        remote_module.DEFAULT_COMMAND_DEVICE: {"orphan": "RAW"},
    }


def test_remote_entity_storage_processing_and_turn_on_off():
    client = FakeClient()
    remote = remote_module.LifeSmartSPOTRemote(None, make_raw_device(), client)
    remote._store = FakeStore({"entities": {remote.unique_id: {"tv": {"power": "ABC"}, "raw": "RAW"}}})
    remote.async_write_ha_state = lambda: None

    asyncio.run(remote._async_load_commands())
    assert remote._get_learned_command("power", "tv") == "ABC"
    assert remote._get_learned_command("raw") == "RAW"
    assert "tv:power" in remote._learned_command_names()
    assert remote._process_ir_code("UkFX") == "RAW"
    assert remote._process_ir_code("not-base64") == "not-base64"

    asyncio.run(remote.async_turn_on())
    asyncio.run(remote.async_turn_off())
    assert remote.is_on is True


def test_remote_send_learn_delete_and_added_to_hass(monkeypatch):
    client = FakeClient()
    remote = remote_module.LifeSmartSPOTRemote(None, make_raw_device(), client)
    remote._store = FakeStore()
    remote.async_write_ha_state = lambda: None
    remote.hass = object()
    monkeypatch.setattr(remote_module, "Store", lambda hass, version, key: remote._store)

    asyncio.run(remote.async_learn_command(command=["power"], command_type="RAW_IR", device="tv"))
    asyncio.run(remote.async_send_command(["power"], device="tv"))
    asyncio.run(remote.async_send_command(["UNKNOWN"], device="other"))
    asyncio.run(remote.async_delete_command(["power"], device="tv"))
    asyncio.run(remote.async_added_to_hass())

    assert client.sent == [("HUB1", "SPOT1", "RAW_IR"), ("HUB1", "other", "UNKNOWN")]
    assert remote.extra_state_attributes["hub_id"] == "HUB1"
