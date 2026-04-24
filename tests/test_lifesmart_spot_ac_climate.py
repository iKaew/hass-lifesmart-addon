import asyncio

from custom_components.lifesmart.const import IR_CATEGORY_AC
from custom_components.lifesmart.spotac_climate import LifeSmartSPOTACClimate


class FakeACClient:
    def __init__(self, ac_codes):
        self.ac_codes = ac_codes
        self.get_ac_codes_calls = []
        self.sent_ir_codes = []

    async def get_ac_codes_async(
        self, category, brand, idx, key, power, mode, temp, wind, swing
    ):
        self.get_ac_codes_calls.append(
            {
                "category": category,
                "brand": brand,
                "idx": idx,
                "key": key,
                "power": power,
                "mode": mode,
                "temp": temp,
                "wind": wind,
                "swing": swing,
            }
        )
        return self.ac_codes

    async def send_ir_code_async(self, hub_id, device_id, ir_code):
        self.sent_ir_codes.append((hub_id, device_id, ir_code))


def make_spot_ac(ac_codes):
    client = FakeACClient(ac_codes)
    climate = LifeSmartSPOTACClimate(
        ha_device=None,
        raw_device_data={
            "name": "SPOT",
            "devtype": "SL_SPOT",
            "agt": "HUB1",
            "me": "SPOT1",
            "ver": "1.0",
        },
        client=client,
        ac_info={"category": IR_CATEGORY_AC, "brand": "aux", "idx": "33.irxs"},
    )
    return climate, client


def test_spot_ac_gets_ir_code_from_api_and_sends_it():
    climate, client = make_spot_ac({"data": "API_IR_CODE"})

    asyncio.run(
        climate._send_ac_command(
            key="temp",
            power=0,
            mode=1,
            temp=24,
            wind=0,
            swing=0,
        )
    )

    assert client.get_ac_codes_calls == [
        {
            "category": IR_CATEGORY_AC,
            "brand": "aux",
            "idx": "33.irxs",
            "key": "temp",
            "power": 0,
            "mode": 1,
            "temp": 24,
            "wind": 0,
            "swing": 0,
        }
    ]
    assert client.sent_ir_codes == [("HUB1", "SPOT1", "API_IR_CODE")]


def test_spot_ac_accepts_list_code_response_from_api():
    climate, client = make_spot_ac([{"data": "API_LIST_IR_CODE"}])

    asyncio.run(
        climate._send_ac_command(
            key="power",
            power=0,
            mode=1,
            temp=25,
            wind=0,
            swing=0,
        )
    )

    assert client.sent_ir_codes == [("HUB1", "SPOT1", "API_LIST_IR_CODE")]
