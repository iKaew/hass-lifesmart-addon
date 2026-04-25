import asyncio
import importlib

cover_module = importlib.import_module("custom_components.lifesmart.cover")


class FakeConfigEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id


class FakeHass:
    def __init__(self, entry_id, devices, exclude_devices=None, exclude_hubs=None, client=None):
        self.data = {
            cover_module.DOMAIN: {
                entry_id: {
                    "devices": devices,
                    "exclude_devices": exclude_devices or [],
                    "exclude_hubs": exclude_hubs or [],
                    "client": client,
                }
            }
        }


class FakeDevice:
    def __init__(self):
        self.calls = []

    async def async_lifesmart_epset(self, type, val, idx):
        self.calls.append((type, val, idx))
        return 0


def make_device(device_type, data, device_id="DEV1", hub_id="HUB1"):
    return {
        "name": "Cover",
        "devtype": device_type,
        "agt": hub_id,
        "me": device_id,
        "data": data,
    }


def test_cover_async_setup_entry_creates_supported_entities():
    devices = [
        make_device("SL_DOOYA", {"P1": {"type": 1, "val": 0x80 | 60}}),
        make_device("SL_CN_IF", {"P1": {"type": 1, "val": 1}}, device_id="FUNC1"),
        make_device("UNKNOWN", {"P1": {"type": 1, "val": 1}}, device_id="SKIP"),
    ]
    hass = FakeHass("entry-1", devices, client=object())
    added = []

    asyncio.run(cover_module.async_setup_entry(hass, FakeConfigEntry(), lambda entities: added.extend(entities)))

    assert len(added) == 2
    assert {entity.entity_id for entity in added} == {
        "cover.sl_dooya_hub1_dev1",
        "cover.sl_cn_if_hub1_func1",
    }


def test_cover_properties_and_commands():
    pos_device = FakeDevice()
    pos_cover = cover_module.LifeSmartCover(
        pos_device,
        make_device("SL_DOOYA", {"P1": {"type": 1, "val": 0x80 | 60}}),
        "P1",
        {"type": 1, "val": 0x80 | 60},
        cover_module.CURTAIN_DEVICE_CONFIG["SL_DOOYA"],
    )
    func_device = FakeDevice()
    func_cover = cover_module.LifeSmartCover(
        func_device,
        make_device("SL_CN_IF", {"P1": {"type": 1, "val": 1}}),
        "P1",
        {"type": 1, "val": 1},
        cover_module.CURTAIN_DEVICE_CONFIG["SL_CN_IF"],
    )

    assert pos_cover.supported_features & cover_module.CoverEntityFeature.SET_POSITION
    assert pos_cover.current_cover_position == 60
    assert pos_cover.is_closed is False
    assert pos_cover.is_opening is True
    assert pos_cover.is_closing is False
    assert pos_cover.should_poll is False

    assert func_cover.current_cover_position is None
    assert func_cover.is_closed is None
    assert func_cover.is_opening is None
    assert func_cover.is_closing is None

    asyncio.run(pos_cover.async_close_cover())
    asyncio.run(pos_cover.async_open_cover())
    asyncio.run(pos_cover.async_stop_cover())
    asyncio.run(pos_cover.async_set_cover_position(position=25))
    asyncio.run(func_cover.async_close_cover())
    asyncio.run(func_cover.async_open_cover())
    asyncio.run(func_cover.async_stop_cover())
    asyncio.run(func_cover.async_set_cover_position(position=50))

    assert pos_device.calls == [("0xCF", 0, "P2"), ("0xCF", 100, "P2"), ("0xCE", 128, "P2"), ("0xCE", 25, "P2")]
    assert func_device.calls == [("0x81", 1, "P3"), ("0x81", 1, "P1"), ("0x81", 1, "P2")]
