"""Tests for the LifeSmart infrared emitter platform."""

import asyncio

import pytest
from infrared_protocols import NECCommand

from custom_components.lifesmart import infrared as infrared_module


class FakeClient:
    def __init__(self, response=None):
        self.response = {"code": 0} if response is None else response
        self.sent = []

    async def send_ir_code_async(self, hub_id, device_id, ir_code):
        self.sent.append((hub_id, device_id, ir_code))
        return self.response


def make_device(device_id="SPOT1", device_type="SL_SPOT"):
    return {
        "name": "Living room SPOT",
        "devtype": device_type,
        "agt": "HUB1",
        "me": device_id,
        "ver": "1.0",
    }


def test_setup_creates_emitters_only_for_included_ir_devices():
    client = FakeClient()
    hass = type(
        "Hass",
        (),
        {
            "data": {
                infrared_module.DOMAIN: {
                    "entry": {
                        "client": client,
                        "devices": [
                            make_device(),
                            make_device("IR1", "SL_P_IR"),
                            make_device("OTHER", "SL_OL"),
                        ],
                        "exclude_devices": ["IR1"],
                        "exclude_hubs": [],
                    }
                }
            }
        },
    )()
    entry = type("Entry", (), {"entry_id": "entry"})()
    added = []

    asyncio.run(
        infrared_module.async_setup_entry(
            hass, entry, lambda entities: added.extend(entities)
        )
    )

    assert len(added) == 1
    assert added[0].unique_id == "sl_spot_hub1_spot1_infrared"
    assert added[0].device_info["identifiers"] == {
        (infrared_module.DOMAIN, "HUB1", "SPOT1")
    }


def test_send_command_converts_nec_command_and_uses_spot_device():
    client = FakeClient()
    emitter = infrared_module.LifeSmartInfraredEmitter(make_device(), client)
    command = NECCommand(address=0x04, command=0x08, modulation=38_000)

    asyncio.run(emitter.async_send_command(command))

    hub_id, device_id, pronto = client.sent[0]
    assert (hub_id, device_id) == ("HUB1", "SPOT1")
    assert pronto.startswith("0000 006D 0022 0000 0156 00AB")
    assert len(pronto.split()) == 72


def test_command_conversion_rejects_invalid_commands():
    class EmptyCommand:
        modulation = 38_000

        @staticmethod
        def get_raw_timings():
            return []

    with pytest.raises(ValueError, match="no timings"):
        infrared_module.command_to_pronto(EmptyCommand())


def test_send_command_reports_lifesmart_api_error():
    client = FakeClient({"code": 10009, "message": "timeout"})
    emitter = infrared_module.LifeSmartInfraredEmitter(make_device(), client)
    command = NECCommand(address=0x04, command=0x08, modulation=38_000)

    with pytest.raises(infrared_module.HomeAssistantError, match="rejected"):
        asyncio.run(emitter.async_send_command(command))
