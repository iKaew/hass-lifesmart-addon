"""Tests for the standalone LifeSmart LAN protocol verifier."""

from __future__ import annotations

import gzip
import struct

import pytest

from scripts.verify_local_protocol import (
    EnumValue,
    FrameBuffer,
    ProtocolError,
    build_config_packet,
    build_state_packet,
    classify_event,
    decode_payload,
    encode_packet,
    encode_value,
    extract_nodes,
    find_first,
    observe_control_event,
)


def test_plain_frame_handles_fragmentation_and_utf8_lengths():
    packet = encode_packet([{"name": "ห้องนั่งเล่น", "req": False}])
    frames = FrameBuffer()

    frames.feed(packet[:7])
    assert frames.pop() is None

    frames.feed(packet[7:])
    frame = frames.pop()

    assert frame is not None
    assert frame.magic == "GL00"
    assert frame.compressed is False
    assert decode_payload(frame.payload) == [
        {"name": "ห้องนั่งเล่น", "req": False}
    ]


def test_protocol_string_preserves_alignment_when_bytes_are_not_utf8():
    # One implicit map containing enum key `name`, then a six-byte string.
    payload = b"\x01\x13\x10\x11\x06abc\x90de"

    assert decode_payload(payload) == [{"name": "abc\ufffdde"}]


def test_protocol_decoder_converts_binary_uuid_to_lifesmart_identifier():
    raw_uuid = bytes.fromhex("03320000c896770100000b3e500cffff")
    payload = b"\x01\x13\x5a\x11\x10" + raw_uuid

    assert decode_payload(payload) == [{"uuid": "AzIAAMiWdwEAAAs-UAz__w"}]


def test_protocol_decoder_keeps_text_uuid_unchanged():
    identifier = "AzIAAMiWdwEAAAs-UAz__w"
    packet = encode_packet([{"uuid": identifier}])
    frames = FrameBuffer()
    frames.feed(packet)

    assert decode_payload(frames.pop().payload) == [{"uuid": identifier}]


def test_protocol_decoder_converts_binary_nid_to_hexadecimal():
    payload = b"\x01\x13\x26\x11\x04\x10\xe6\x40\x7c"

    assert decode_payload(payload) == [{"nid": "10e6407c"}]


def test_protocol_decoder_keeps_text_nid_unchanged():
    packet = encode_packet([{"nid": "0020"}])
    frames = FrameBuffer()
    frames.feed(packet)

    assert decode_payload(frames.pop().payload) == [{"nid": "0020"}]


@pytest.mark.parametrize("reserved", [True, False])
def test_gzip_frame_accepts_both_observed_length_offsets(reserved):
    inner = encode_packet([{"ret": {"base": {1: "hub/base"}}}])
    compressed = gzip.compress(inner)
    if reserved:
        packet = b"ZZ00\x00\x00" + struct.pack(">I", len(inner)) + compressed
    else:
        packet = b"ZZ00" + struct.pack(">I", len(inner)) + compressed

    frames = FrameBuffer()
    frames.feed(packet)
    frame = frames.pop()

    assert frame is not None
    assert frame.magic == "ZZ00"
    assert frame.compressed is True
    assert decode_payload(frame.payload) == [{"ret": {"base": {1: "hub/base"}}}]


def test_frame_buffer_preserves_a_following_frame_after_gzip():
    inner = encode_packet([{"ret": 1}])
    first = (
        b"ZZ00\x00\x00"
        + struct.pack(">I", len(inner))
        + gzip.compress(inner)
    )
    second = encode_packet([{"name": "next"}])
    frames = FrameBuffer()
    frames.feed(first + second)

    assert decode_payload(frames.pop().payload) == [{"ret": 1}]
    assert decode_payload(frames.pop().payload) == [{"name": "next"}]


def test_declared_plain_frame_size_is_bounded():
    frames = FrameBuffer(max_frame=16)
    frames.feed(b"GL00\x00\x00" + struct.pack(">I", 17))

    with pytest.raises(ProtocolError, match="exceeds safety limit"):
        frames.pop()


def test_login_node_extraction_uses_indexed_protocol_values():
    message = [
        {
            "ret": {
                4: {
                    "base": {0: "unused", 1: "node/base"},
                    "agt": {0: "unused", 1: "node/agent"},
                }
            }
        }
    ]

    assert extract_nodes(message) == ("node/base", "node/agent")


def test_config_request_is_read_only_and_targets_the_base_node():
    packet = build_config_packet("node/base")
    frames = FrameBuffer()
    frames.feed(packet)
    message = decode_payload(frames.pop().payload)

    assert find_first(message, "node") == "node/base/me/ep"
    assert find_first(message, "req") is False
    assert find_first(message, "_") == "eps"
    assert find_first(message, "act") == EnumValue(91)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("enum:91", b"\x13\x5b"),
        ("enum:14", b"\x13\x0e"),
        ("enum:0", b"\x13\x00"),
        ("enum:255", b"\x13\xff"),
        ("enum:val", b"\x13\x29"),
    ],
)
def test_numeric_and_named_enum_references_use_wire_enum_type(reference, expected):
    assert encode_value(reference) == expected


@pytest.mark.parametrize("reference", ["enum:notanumber", "enum:-1", "enum:256"])
def test_invalid_enum_references_remain_protocol_strings(reference):
    encoded = encode_value(reference)

    assert encoded[0] == 0x11
    assert encoded.endswith(reference.encode("utf-8"))


def test_push_event_classification():
    assert classify_event([{"_schg": {"node/ep/device/m/P1": {}}}]) == (
        "state_change"
    )
    assert classify_event([{"_sdel": {"node/ep/device": True}}]) == (
        "device_deleted"
    )
    assert classify_event([{"ret": {}}]) == "other"


def test_state_command_targets_one_endpoint_channel():
    packet = build_state_packet("node/agent", "DEVICE1", "P1", True)
    frames = FrameBuffer()
    frames.feed(packet)
    message = decode_payload(frames.pop().payload)

    assert find_first(message, "node") == "node/agent/ep"
    assert find_first(message, "devid") == "DEVICE1"
    assert find_first(message, "key") == "P1"
    assert find_first(message, "val") == 1
    assert find_first(message, "type") == 128
    assert find_first(message, "act") == "rfSetA"


def test_control_event_observation_matches_device_channel_and_state():
    event = [
        {
            "_schg": {
                "node/ep/DEVICE1/m/P1": {
                    "chg": {"val": 1, "type": 129}
                }
            }
        }
    ]

    assert observe_control_event(event, "DEVICE1", "P1") is True
