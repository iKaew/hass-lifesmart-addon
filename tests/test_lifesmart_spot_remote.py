import asyncio

from custom_components.lifesmart.remote import LifeSmartSPOTRemote


class FakeClient:
    def __init__(self):
        self.sent = []

    async def send_ir_code_async(self, hub_id, device_id, ir_code):
        self.sent.append((hub_id, device_id, ir_code))


class FakeStore:
    def __init__(self, data=None):
        self.data = data

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data


def make_remote(store=None):
    client = FakeClient()
    remote = LifeSmartSPOTRemote(
        ha_device=None,
        raw_device_data={
            "name": "SPOT",
            "devtype": "SL_SPOT",
            "agt": "HUB1",
            "me": "SPOT1",
            "ver": "1.0",
        },
        client=client,
    )
    remote._store = store or FakeStore()
    remote.async_write_ha_state = lambda: None
    return remote, client


def test_spot_learn_command_saves_ir_data_locally():
    remote, _client = make_remote()

    asyncio.run(
        remote.async_learn_command(command=["power"], command_type="018B4F", device="tv")
    )

    assert remote._learned_commands == {"tv": {"power": "018B4F"}}
    assert remote._store.data == {
        "entities": {
            "remote.sl_spot_hub1_spot1_remote": {"tv": {"power": "018B4F"}}
        }
    }


def test_spot_send_command_uses_saved_ir_data():
    remote, client = make_remote(
        FakeStore(
            {
                "entities": {
                    "remote.sl_spot_hub1_spot1_remote": {"tv": {"power": "018B4F"}}
                }
            }
        )
    )

    asyncio.run(remote.async_send_command(["power"], device="tv"))

    assert client.sent == [("HUB1", "SPOT1", "018B4F")]


def test_spot_send_command_falls_back_to_raw_ir_data():
    remote, client = make_remote()

    asyncio.run(remote.async_send_command(["RAW_IR"], device="OTHER_DEVICE"))

    assert client.sent == [("HUB1", "OTHER_DEVICE", "RAW_IR")]


def test_spot_delete_command_removes_saved_ir_data():
    remote, _client = make_remote(
        FakeStore(
            {
                "entities": {
                    "remote.sl_spot_hub1_spot1_remote": {"tv": {"power": "018B4F"}}
                }
            }
        )
    )

    asyncio.run(remote.async_delete_command(["power"], device="tv"))

    assert remote._learned_commands == {}
    assert remote._store.data == {"entities": {"remote.sl_spot_hub1_spot1_remote": {}}}
