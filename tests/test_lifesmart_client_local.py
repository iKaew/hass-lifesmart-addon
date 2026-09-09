"""Tests for the runtime LifeSmart local protocol client."""

from __future__ import annotations

import asyncio
import gzip
import logging
import struct
from unittest.mock import AsyncMock, Mock

import pytest

import custom_components.lifesmart.lifesmart_client_local as local_module
from custom_components.lifesmart.lifesmart_client_local import (
    DISCOVERY_BROADCAST_HOST,
    DISCOVERY_BROADCAST_PORT,
    DISCOVERY_FIND_AGENT,
    DISCOVERY_MULTICAST_HOST,
    DISCOVERY_MULTICAST_PORT,
    DISCOVERY_SEARCH,
    EnumValue,
    FrameBuffer,
    LocalLifeSmartClient,
    async_discover_local_hubs,
    build_control_packet,
    build_ir_code_packet,
    build_login_packet,
    build_scene_query_packet,
    build_scene_run_packet,
    decode_payload,
    encode_packet,
    find_first,
)


@pytest.mark.parametrize("response", [[{"err": "denied"}], [{"ret": None}]])
def test_local_login_rejects_invalid_credentials(response):
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "wrong")
        client._writer = Mock()
        client._send = AsyncMock()
        client._read_until = AsyncMock(return_value=response)

        assert (await client.login_async())["code"] == "failure"
        assert client._agent_node is None
        assert client.hub_id == "192.0.2.10"

    asyncio.run(scenario())


@pytest.mark.parametrize("nodes", [{}, {"base": {1: "hub"}}, {"base": 7, "agt": "hub/me"}])
def test_local_login_rejects_missing_or_invalid_nodes(nodes):
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        client._writer = Mock()
        client._send = AsyncMock()
        client._read_until = AsyncMock(return_value=[{"ret": nodes}])

        with pytest.raises(local_module.LocalProtocolError, match="hub nodes"):
            await client.login_async()
        assert client._agent_node is None

    asyncio.run(scenario())


def test_local_reader_handles_split_and_consecutive_frames():
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        first = encode_packet([{"ret": "first"}])
        second = encode_packet([{"ret": "second"}])
        client._reader = Mock(read=AsyncMock(side_effect=[first[:5], first[5:] + second, b""]))

        assert await client._read_frame() == [{"ret": "first"}]
        assert await client._read_frame() == [{"ret": "second"}]
        assert client._reader.read.await_count == 2
        with pytest.raises(ConnectionError, match="closed"):
            await client._read_frame()

    asyncio.run(scenario())


def test_local_read_until_skips_notifications_and_times_out():
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin", timeout=0.01)
        response = [{"ret": "ok"}]
        client._read_frame = AsyncMock(side_effect=[[{"noti": "datachg"}], response])
        assert await client._read_until(lambda msg: find_first(msg, "ret") is not local_module.MISSING) == response

        async def pending_read():
            await asyncio.Event().wait()

        client._read_frame = pending_read
        with pytest.raises(TimeoutError):
            await client._read_until(lambda msg: True)

    asyncio.run(scenario())


def test_local_listener_recovers_after_rejected_reconnect(monkeypatch):
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        original_writer = Mock()
        rejected_writer = Mock()
        recovered_writer = Mock()
        client._writer = original_writer
        client._read_frame = AsyncMock(side_effect=[ConnectionError("lost"), asyncio.CancelledError()])
        client.get_all_device_async = AsyncMock(return_value=[])
        attempts = 0

        async def login():
            nonlocal attempts
            attempts += 1
            client._writer = rejected_writer if attempts == 1 else recovered_writer
            return {"code": "failure" if attempts == 1 else "success"}

        client.login_async = login
        monkeypatch.setattr(local_module, "RECONNECT_DELAY", 0)
        on_connection = Mock()
        with pytest.raises(asyncio.CancelledError):
            await client._listen(Mock(), on_connection)

        original_writer.close.assert_called_once()
        rejected_writer.close.assert_called_once()
        recovered_writer.close.assert_not_called()
        assert attempts == 2
        client.get_all_device_async.assert_awaited_once()
        assert [call.args for call in on_connection.call_args_list] == [
            (False, "ConnectionError"), (True, None)
        ]

    asyncio.run(scenario())


def test_local_listener_starts_once_and_close_cleans_up():
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        writer = Mock(wait_closed=AsyncMock(side_effect=OSError("closed")))
        client._writer = writer
        started = asyncio.Event()

        async def listen(*args):
            started.set()
            await asyncio.Event().wait()

        client._listen = listen
        connection = Mock()
        client.start_listener(Mock(), connection)
        task = client._listener_task
        client.start_listener(Mock(), connection)
        assert client._listener_task is task
        connection.assert_called_once_with(True, None)
        await started.wait()
        await client.async_close()
        await client.async_close()
        assert task.cancelled()
        assert client._listener_task is None
        assert client._reader is None
        assert client._writer is None
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    asyncio.run(scenario())


def test_local_discovery_parses_and_merges_captured_advertisements():
    hubs = {}
    protocol = local_module._LifeSmartDiscoveryProtocol(hubs)
    protocol.datagram_received(
        b"AGT=hub_id;NAME=?;URL=GL://*:9876",
        ("192.168.1.115", DISCOVERY_BROADCAST_PORT),
    )
    protocol.datagram_received(
        b"LSID=hub_id\nMGAMOD=LSJZX1K\nWLAN=WPA\nNAME=?\n"
        b"MGAFWVER=1317\nVER=1.0.94p10",
        ("192.168.1.115", DISCOVERY_BROADCAST_PORT),
    )

    assert list(hubs.values()) == [
        local_module.DiscoveredLifeSmartHub(
            host="192.168.1.115",
            hub_id="hub_id",
            port=9876,
            model="LSJZX1K",
            firmware="1317",
            protocol_version="1.0.94p10",
        )
    ]
    assert list(hubs.values())[0].display_name == "LSJZX1K (192.168.1.115:9876)"


def test_local_discovery_rejects_untrusted_or_unrelated_datagrams():
    assert (
        local_module.parse_local_discovery_response(
            DISCOVERY_SEARCH, "192.168.1.115"
        )
        is None
    )
    assert (
        local_module.parse_local_discovery_response(
            b"AGT=../../bad;URL=GL://*:8888", "192.168.1.115"
        )
        is None
    )
    assert (
        local_module.parse_local_discovery_response(
            b"AGT=valid;URL=GL://attacker.example:1234", "not-an-ip"
        )
        is None
    )


def test_local_discovery_sends_packet_confirmed_probes_and_closes(monkeypatch):
    sent = []
    transports = []

    class FakeTransport:
        def __init__(self, source_port):
            self.source_port = source_port
            self.closed = False
            transports.append(self)

        def sendto(self, payload, destination):
            sent.append((self.source_port, payload, destination))

        def close(self):
            self.closed = True

    async def fake_open(source_port, hubs):
        if source_port == 60021:
            protocol = local_module._LifeSmartDiscoveryProtocol(hubs)
            protocol.datagram_received(
                b"LSID=hub_id\nMGAMOD=LSJZX1K\nVER=1.0.94p10",
                ("192.168.1.115", DISCOVERY_BROADCAST_PORT),
            )
        return FakeTransport(source_port)

    monkeypatch.setattr(local_module, "_async_open_discovery_transport", fake_open)

    hubs = asyncio.run(async_discover_local_hubs(timeout=0))

    assert hubs[0].host == "192.168.1.115"
    assert set(sent) == {
        (
            60021,
            DISCOVERY_SEARCH,
            (DISCOVERY_BROADCAST_HOST, DISCOVERY_BROADCAST_PORT),
        ),
        (
            60021,
            DISCOVERY_SEARCH,
            (DISCOVERY_MULTICAST_HOST, DISCOVERY_MULTICAST_PORT),
        ),
        (
            60001,
            DISCOVERY_FIND_AGENT,
            (DISCOVERY_BROADCAST_HOST, DISCOVERY_BROADCAST_PORT),
        ),
        (
            60001,
            DISCOVERY_SEARCH,
            (DISCOVERY_BROADCAST_HOST, DISCOVERY_BROADCAST_PORT),
        ),
        (
            60001,
            DISCOVERY_FIND_AGENT,
            (DISCOVERY_MULTICAST_HOST, DISCOVERY_MULTICAST_PORT),
        ),
        (
            60001,
            DISCOVERY_SEARCH,
            (DISCOVERY_MULTICAST_HOST, DISCOVERY_MULTICAST_PORT),
        ),
    }
    assert all(transport.closed for transport in transports)


def test_local_login_uses_stable_homeassistant_node():
    packet = build_login_packet("secret")
    frames = FrameBuffer()
    frames.feed(packet)
    message = decode_payload(frames.pop())

    assert find_first(message, "node") == "homeassistant"


def test_runtime_frame_decoder_accepts_compressed_protocol_frames():
    inner = encode_packet([{"ret": {"base": {1: "node/base"}}}])
    packet = b"ZZ00\x00\x00" + struct.pack(">I", len(inner)) + gzip.compress(inner)
    frames = FrameBuffer()
    frames.feed(packet)

    assert decode_payload(frames.pop()) == [{"ret": {"base": {1: "node/base"}}}]


def test_runtime_decoder_converts_binary_uuid_to_lifesmart_identifier():
    raw_uuid = bytes.fromhex("03320000c896770100000b3e500cffff")
    payload = b"\x01\x13\x5a\x11\x10" + raw_uuid

    assert decode_payload(payload) == [{"uuid": "AzIAAMiWdwEAAAs-UAz__w"}]


def test_runtime_decoder_keeps_text_uuid_unchanged():
    identifier = "AzIAAMiWdwEAAAs-UAz__w"
    packet = encode_packet([{"uuid": identifier}])
    frames = FrameBuffer()
    frames.feed(packet)

    assert decode_payload(frames.pop()) == [{"uuid": identifier}]


def test_runtime_decoder_converts_binary_nid_to_hexadecimal():
    payload = b"\x01\x13\x26\x11\x04\x10\xe6\x40\x7c"

    assert decode_payload(payload) == [{"nid": "10e6407c"}]


def test_runtime_decoder_keeps_text_nid_unchanged():
    packet = encode_packet([{"nid": "0020"}])
    frames = FrameBuffer()
    frames.feed(packet)

    assert decode_payload(frames.pop()) == [{"nid": "0020"}]


def test_local_client_logs_each_decoded_response_or_event(caplog):
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        reader = asyncio.StreamReader()
        reader.feed_data(encode_packet([{"ret": {"status": "ok"}}]))
        client._reader = reader
        return await client._read_frame()

    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.lifesmart.lifesmart_client_local",
    ):
        message = asyncio.run(scenario())

    assert message == [{"ret": {"status": "ok"}}]
    assert "LifeSmart local decoded response/event from 192.0.2.10:8888" in caplog.text
    assert "'status': 'ok'" in caplog.text


def test_control_packet_uses_verified_even_wire_type():
    packet = build_control_packet("node/HUB1", "DEVICE1", "P1", 1, 0x81)
    frames = FrameBuffer()
    frames.feed(packet)
    message = decode_payload(frames.pop())

    assert find_first(message, "node") == "node/HUB1/ep"
    assert find_first(message, "devid") == "DEVICE1"
    assert find_first(message, "key") == "P1"
    assert find_first(message, "val") == 1
    assert find_first(message, "type") == 0x80


def test_ir_code_packet_uses_upstream_local_sendcode_shape():
    packet = build_ir_code_packet("node/HUB1/me", "SPOT1", "0000 006D 0001 0000")
    frames = FrameBuffer()
    frames.feed(packet)
    message = decode_payload(frames.pop())

    assert find_first(message, "node") == "node/HUB1/me/ep"
    assert find_first(message, "act") == "epCmdA"
    assert find_first(message, "ctrlcmd") == "sendcode"
    assert find_first(message, "valtag") == "m"
    assert find_first(message, "cmd") == "ctrl"
    assert find_first(message, "devid") == "SPOT1"
    assert find_first(message, "param") == {
        "type": 1,
        "data": "0000 006D 0001 0000",
    }


def test_local_scene_query_packet_uses_ai_object_tree():
    packet = build_scene_query_packet("node/HUB1/me")
    frames = FrameBuffer()
    frames.feed(packet)
    message = decode_payload(frames.pop())

    assert find_first(message, "node") == "node/HUB1/me/ai"
    action = find_first(message, "act")
    assert isinstance(action, EnumValue)
    assert action.code == 91
    assert find_first(message, "cron_name") is False
    assert find_first(message, "cls") is False
    assert find_first(message, "name") is False


def test_local_scene_run_packet_uses_verified_runa_shape():
    packet = build_scene_run_packet("node/HUB1/me", "AI1787037704")
    frames = FrameBuffer()
    frames.feed(packet)
    message = decode_payload(frames.pop())

    assert find_first(message, "node") == "node/HUB1/me/ai"
    assert find_first(message, "act") == "RunA"
    assert find_first(message, "cron_name") == "AI1787037704"


def test_local_scene_discovery_filters_and_normalizes_ai_records():
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        client._agent_node = "node/HUB1/me"
        client._hub_id = "HUB1"
        packets = []
        response = [
            {
                "ret": {
                    1: {
                        "ai": {
                            "AI1": {"cls": "scene", "name": " Coffee Scene "},
                            "AI2": {
                                "cls": "groupirc",
                                "name": "Watch television",
                            },
                            "AI_IR_1": {"cls": "irkey", "name": "Remote"},
                            "TRIGGER1": {"cls": "trigger", "name": "Alarm"},
                            "AI3": {"cls": "scene", "name": ""},
                        }
                    }
                }
            }
        ]

        async def capture(packet):
            packets.append(packet)

        async def read_until(predicate):
            assert predicate(response)
            return response

        client._send = capture
        client._read_until = read_until
        scenes = await client.get_all_scene_async("HUB1")
        return client, packets, scenes

    client, packets, scenes = asyncio.run(scenario())

    assert scenes == [
        {"id": "AI1", "name": "Coffee Scene"},
        {"id": "AI2", "name": "Watch television"},
        {"id": "AI3", "name": "LifeSmart Scene AI3"},
    ]
    assert client._scene_ids == {"AI1", "AI2", "AI3"}
    assert len(packets) == 1


def test_local_scene_activation_sends_only_discovered_scene():
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        client._agent_node = "node/HUB1/me"
        client._hub_id = "HUB1"
        client._scene_ids = {"AI1"}
        packets = []

        async def capture(packet):
            packets.append(packet)

        client._send = capture
        accepted = await client.set_scene_async("HUB1", "AI1")
        unknown = await client.set_scene_async("HUB1", "AI_IR_1")
        wrong_hub = await client.set_scene_async("HUB2", "AI1")
        return packets, accepted, unknown, wrong_hub

    packets, accepted, unknown, wrong_hub = asyncio.run(scenario())
    frames = FrameBuffer()
    frames.feed(packets[0])
    message = decode_payload(frames.pop())

    assert accepted == 0
    assert unknown["code"] == "failure"
    assert wrong_hub["code"] == "failure"
    assert len(packets) == 1
    assert find_first(message, "act") == "RunA"
    assert find_first(message, "cron_name") == "AI1"


def test_local_switch_on_and_off_send_expected_endpoint_packets():
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        client._agent_node = "node/HUB1"
        packets = []

        async def capture(packet):
            packets.append(packet)

        client._send = capture

        assert await client.turn_on_light_swith_async("P1", "HUB1", "DEVICE1") == 0
        assert await client.turn_off_light_swith_async("P1", "HUB1", "DEVICE1") == 0
        return packets

    packets = asyncio.run(scenario())
    messages = []
    for packet in packets:
        frames = FrameBuffer()
        frames.feed(packet)
        messages.append(decode_payload(frames.pop()))

    assert [find_first(message, "node") for message in messages] == [
        "node/HUB1/ep",
        "node/HUB1/ep",
    ]
    assert [find_first(message, "devid") for message in messages] == [
        "DEVICE1",
        "DEVICE1",
    ]
    assert [find_first(message, "key") for message in messages] == ["P1", "P1"]
    assert [find_first(message, "val") for message in messages] == [1, 0]
    assert [find_first(message, "type") for message in messages] == [0x80, 0x80]


def test_local_ir_send_accepts_sendcodes_wrapper_and_rejects_non_spot():
    async def scenario():
        client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
        client._agent_node = "node/HUB1/me"
        client._hub_id = "HUB1"
        client._devices = [
            {
                "agt": "HUB1",
                "me": "SPOT1",
                "devtype": "SL_SPOT",
                "name": "SPOT",
                "data": {},
            },
            {
                "agt": "HUB1",
                "me": "LOCK1",
                "devtype": "SL_LK_LS",
                "name": "Lock",
                "data": {},
            },
        ]
        packets = []

        async def capture(packet):
            packets.append(packet)

        client._send = capture
        result = await client.send_ir_code_async(
            "HUB1",
            "SPOT1",
            '[{"param": {"data": "CODE_ONE", "type": 1}}, '
            '{"param": {"data": "CODE_TWO", "type": 1}}]',
        )
        direct_result = await client.send_ir_code_async("HUB1", "SPOT1", "123")
        with pytest.raises(ValueError, match="not a supported SPOT"):
            await client.send_ir_code_async("HUB1", "LOCK1", "CODE")
        return result, direct_result, packets

    result, direct_result, packets = asyncio.run(scenario())
    messages = []
    for packet in packets:
        frames = FrameBuffer()
        frames.feed(packet)
        messages.append(decode_payload(frames.pop()))

    assert result == 0
    assert direct_result == 0
    assert [find_first(message, "data") for message in messages] == [
        "CODE_ONE",
        "CODE_TWO",
        "123",
    ]


def test_local_client_authenticates_discovers_and_normalizes_devices(monkeypatch):
    async def scenario():
        requests = []
        responses = [
            encode_packet(
                [
                    {
                        "ret": {
                            "base": {1: "node/base"},
                            "agt": {1: "node/HUB1/me"},
                        }
                    }
                ]
            ),
            encode_packet(
                [
                    {
                        "eps": {
                            "DEVICE1": {
                                "name": "Kitchen",
                                "cls": "SL_SW_IF1",
                                "agtid": "all",
                                "ver": "1.2.3",
                                "_chd": {
                                    "m": {
                                        "_chd": {
                                            "P1": {
                                                "name": "Light",
                                                "type": 129,
                                                "val": 1,
                                            }
                                        }
                                    }
                                },
                            }
                        }
                    }
                ]
            ),
        ]
        reader = asyncio.StreamReader()

        class FakeWriter:
            def write(self, packet):
                frames = FrameBuffer()
                frames.feed(packet)
                requests.append(decode_payload(frames.pop()))
                reader.feed_data(responses[len(requests) - 1])

            async def drain(self):
                return None

            def close(self):
                return None

            async def wait_closed(self):
                return None

        async def open_connection(host, port):
            assert (host, port) == ("127.0.0.1", 8888)
            return reader, FakeWriter()

        monkeypatch.setattr(asyncio, "open_connection", open_connection)
        client = LocalLifeSmartClient("127.0.0.1", 8888, "admin")
        try:
            assert await client.login_async() == {"code": "success"}
            assert client.hub_id == "HUB1"
            devices = await client.get_all_device_async()
        finally:
            await client.async_close()

        assert find_first(requests[0], "uid") == "admin"
        assert find_first(requests[0], "pwd") == "admin"
        assert devices == [
            {
                "me": "DEVICE1",
                "agt": "HUB1",
                "devtype": "SL_SW_IF1",
                "name": "Kitchen",
                "ver": "1.2.3",
                "stat": 1,
                "data": {"P1": {"name": "Light", "type": 129, "val": 1}},
            }
        ]

    asyncio.run(scenario())


def test_local_push_message_is_converted_to_cloud_event_shape():
    client = LocalLifeSmartClient("192.0.2.10", 8888, "admin")
    client._devices = [
        {
            "me": "DEVICE1",
            "agt": "HUB1",
            "devtype": "SL_SW_IF1",
            "data": {"P1": {"type": 128, "val": 0}},
        }
    ]

    message = [
        {"_schg": {"node/HUB1/ep/DEVICE1/m/P1": {"chg": {"type": 129, "val": 1}}}}
    ]
    events = client._events_from_message(message)

    assert events == [
        {
            "devtype": "SL_SW_IF1",
            "agt": "HUB1",
            "me": "DEVICE1",
            "idx": "P1",
            "type": 129,
            "val": 1,
        }
    ]

    assert client._cloud_events_from_message(message) == [
        {
            "type": "io",
            "msg": {
                "devtype": "SL_SW_IF1",
                "agt": "HUB1",
                "me": "DEVICE1",
                "idx": "P1",
                "type": 129,
                "val": 1,
            },
        }
    ]


def test_local_timestamp_only_notification_is_not_a_state_event():
    client = LocalLifeSmartClient("192.168.1.115", 8888, "admin")
    client._devices = [
        {
            "me": "4076",
            "agt": "HUB1",
            "devtype": "SL_SW_MJ1",
            "data": {"P1": {"type": 128, "val": 0}},
        }
    ]

    events = client._events_from_message(
        [
            {
                "_schg": {
                    "hub/me/ep/4076/m/P1": {
                        "del": {},
                        "chg": {
                            "ts": {
                                "kind": "timestamp",
                                "index": 212,
                                "value": 13975482112,
                            }
                        },
                    }
                }
            }
        ]
    )

    assert events == []


def test_logged_multi_channel_heartbeat_produces_no_cloud_entity_updates():
    client = LocalLifeSmartClient("192.168.1.115", 8888, "admin")
    client._devices = [
        {
            "me": "407a",
            "agt": "HUB1",
            "devtype": "SL_P",
            "data": {
                channel: {"type": 128, "val": 0}
                for channel in ("P1", "P2", "P3", "P4", "P5", "P6", "P7")
            },
        }
    ]
    timestamp = {"kind": "timestamp", "index": 158, "value": 13975482583}
    changes = {
        f"hub/me/ep/407a/m/{channel}": {
            "del": {},
            "chg": {"ts": timestamp},
        }
        for channel in ("P3", "P1", "P4", "P2", "P5", "P7", "P6")
    }
    changes["hub/me/ep/407a/s"] = {
        "del": {},
        "chg": {"heart": timestamp},
    }

    assert client._cloud_events_from_message([{"_schg": changes}]) == []


def test_real_407a_value_change_matches_cloud_websocket_event_structure():
    client = LocalLifeSmartClient("192.168.1.115", 8888, "admin")
    client._devices = [
        {
            "me": "407a",
            "agt": "HUB1",
            "devtype": "SL_P",
            "data": {"P6": {"type": 0, "val": 0}},
        }
    ]
    message = [
        {"to": "*", "from": "mga", "noti": "datachg"},
        {
            "_schg": {
                "hub/me/ep/407a/m/P6": {
                    "del": {},
                    "chg": {"type": 1, "val": 1},
                }
            }
        },
    ]

    assert client._cloud_events_from_message(message) == [
        {
            "type": "io",
            "msg": {
                "devtype": "SL_P",
                "agt": "HUB1",
                "me": "407a",
                "idx": "P6",
                "type": 1,
                "val": 1,
            },
        }
    ]


def test_local_discovery_normalizes_logged_class_and_wrapped_rgb_value():
    client = LocalLifeSmartClient("192.168.1.115", 8888, "admin")
    client._hub_id = "HUB_NODE"

    devices = client._normalize_devices(
        {
            "407c": {
                "agtid": "all",
                "name": "Master bedroom",
                "cls": "SL_SPOT_V1",
                "_chd": {
                    "m": {
                        "_chd": {
                            "RGB": {
                                "type": 254,
                                "val": {
                                    "kind": "timestamp",
                                    "index": 128,
                                    "value": 19804569,
                                },
                            }
                        }
                    }
                },
            },
            "4075": {
                "agtid": "all",
                "name": "Stairway",
                "cls": "SL_SW_MJ1_V1",
                "_chd": {"m": {"_chd": {"P1": {"type": 129, "val": 1}}}},
            },
        }
    )

    assert [device["devtype"] for device in devices] == [
        "SL_SPOT",
        "SL_SW_MJ1",
    ]
    assert {device["agt"] for device in devices} == {"HUB_NODE"}
    assert devices[0]["data"]["RGB"]["val"] == 19804569


def test_local_discovery_preserves_semantic_device_variant_suffixes():
    client = LocalLifeSmartClient("192.168.1.115", 8888, "admin")

    assert client._normalize_device_type("SL_P_V1") == "SL_P"
    assert client._normalize_device_type("SL_P_V2") == "SL_P_V2"
    assert client._normalize_device_type("SL_P_IR_V2") == "SL_P_IR_V2"
