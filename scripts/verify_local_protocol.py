#!/usr/bin/env python3
"""Safely probe the read-only portions of the LifeSmart LAN protocol."""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import json
import os
import struct
import sys
import time
import uuid
import zlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

PLAIN_MAGIC = b"GL00"
GZIP_MAGIC = b"ZZ00"
GZIP_STREAM_MAGIC = b"\x1f\x8b"
HEADER_SIZE = 10
DEFAULT_PORT = 8888
DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_FRAME = 8 * 1024 * 1024
BLOCKED_CONTROL_TYPE_PREFIXES = ("SL_LK", "V_LOCK")

# These are wire-level field identifiers, not Home Assistant constants.
KEY_NAMES = {
    2: "timestamp",
    3: "req",
    4: "args",
    7: "valtag",
    9: "act",
    10: "node",
    11: "ret",
    13: "cron_name",
    16: "name",
    21: "ts",
    22: "devid",
    38: "nid",
    39: "cls",
    40: "rf_button_status",
    41: "val",
    42: "ver",
    46: "cgy",
    47: "key",
    53: "response_token",
    78: "type",
    89: "icon",
    90: "uuid",
    92: "act_change",
    106: "_chd",
    113: "agtid",
    119: "tmzone",
    120: "rf_pair",
    121: "valtag",
    122: "valts",
    135: "dark",
    136: "bright",
}
KEY_CODES = {name: code for code, name in KEY_NAMES.items()}
MISSING = object()


class ProtocolError(RuntimeError):
    """The peer returned a malformed or unsupported protocol message."""


class ProbeError(RuntimeError):
    """The protocol probe could not complete."""


@dataclass(frozen=True, slots=True)
class EnumValue:
    """A numeric enum used by the LifeSmart binary encoding."""

    code: int

    @property
    def name(self) -> str | None:
        """Return the known symbolic name, if any."""
        return KEY_NAMES.get(self.code)


@dataclass(frozen=True, slots=True)
class TimestampValue:
    """A timestamp-like value from the LifeSmart binary encoding."""

    index: int
    value: int


@dataclass(frozen=True, slots=True)
class Frame:
    """One decoded transport frame."""

    payload: bytes
    magic: str
    compressed: bool
    wire_size: int


class Cursor:
    """Bounds-checked reader for one complete packet payload."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    @property
    def remaining(self) -> int:
        """Return the number of unread bytes."""
        return len(self.data) - self.pos

    def read(self, size: int) -> bytes:
        """Read exactly size bytes or fail."""
        if size < 0 or self.pos + size > len(self.data):
            raise ProtocolError(
                f"truncated value at offset {self.pos}: need {size} bytes"
            )
        value = self.data[self.pos : self.pos + size]
        self.pos += size
        return value

    def read_byte(self) -> int:
        """Read one unsigned byte."""
        return self.read(1)[0]


class FrameBuffer:
    """Incrementally extract plain or gzip-compressed transport frames."""

    def __init__(self, max_frame: int = DEFAULT_MAX_FRAME) -> None:
        self.max_frame = max_frame
        self._buffer = bytearray()

    def feed(self, data: bytes) -> None:
        """Append received bytes."""
        self._buffer.extend(data)
        if len(self._buffer) > self.max_frame * 2 + HEADER_SIZE:
            raise ProtocolError("wire buffer exceeded its safety limit")

    def pop(self) -> Frame | None:
        """Return the next complete frame, or None when more bytes are needed."""
        if len(self._buffer) < 4:
            return None

        magic = bytes(self._buffer[:4])
        if magic == PLAIN_MAGIC:
            return self._pop_plain()
        if magic == GZIP_MAGIC:
            return self._pop_gzip()
        raise ProtocolError(f"unexpected frame magic {magic!r}")

    def _pop_plain(self) -> Frame | None:
        if len(self._buffer) < HEADER_SIZE:
            return None
        payload_size = struct.unpack(">I", self._buffer[6:10])[0]
        if payload_size > self.max_frame:
            raise ProtocolError(
                f"declared payload {payload_size} exceeds safety limit"
            )
        frame_size = HEADER_SIZE + payload_size
        if len(self._buffer) < frame_size:
            return None

        payload = bytes(self._buffer[HEADER_SIZE:frame_size])
        del self._buffer[:frame_size]
        return Frame(payload, "GL00", False, frame_size)

    def _gzip_layout(self) -> tuple[int, int] | None:
        """Detect gzip framing with or without the two reserved bytes."""
        if len(self._buffer) >= 12 and self._buffer[10:12] == GZIP_STREAM_MAGIC:
            return 10, struct.unpack(">I", self._buffer[6:10])[0]
        if len(self._buffer) >= 10 and self._buffer[8:10] == GZIP_STREAM_MAGIC:
            return 8, struct.unpack(">I", self._buffer[4:8])[0]
        if len(self._buffer) < 12:
            return None
        raise ProtocolError("compressed frame does not contain a gzip stream")

    def _pop_gzip(self) -> Frame | None:
        layout = self._gzip_layout()
        if layout is None:
            return None
        payload_offset, declared_size = layout
        if declared_size > self.max_frame:
            raise ProtocolError(
                f"declared expanded payload {declared_size} exceeds safety limit"
            )

        compressed = bytes(self._buffer[payload_offset:])
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            expanded = decoder.decompress(compressed, self.max_frame + 1)
        except zlib.error as err:
            raise ProtocolError(f"invalid gzip frame: {err}") from err

        if len(expanded) > self.max_frame or decoder.unconsumed_tail:
            raise ProtocolError("expanded payload exceeded its safety limit")
        if not decoder.eof:
            return None

        expanded += decoder.flush()
        if len(expanded) != declared_size:
            raise ProtocolError(
                "compressed frame size mismatch: "
                f"declared {declared_size}, decoded {len(expanded)}"
            )

        compressed_size = len(compressed) - len(decoder.unused_data)
        wire_size = payload_offset + compressed_size
        del self._buffer[:wire_size]

        if expanded[:4] in (PLAIN_MAGIC, GZIP_MAGIC):
            nested = FrameBuffer(self.max_frame)
            nested.feed(expanded)
            inner = nested.pop()
            if inner is None or nested._buffer:
                raise ProtocolError("compressed payload is not one complete frame")
            return Frame(inner.payload, "ZZ00", True, wire_size)

        return Frame(expanded, "ZZ00", True, wire_size)


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint cannot be negative")
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _decode_varint(cursor: Cursor) -> int:
    value = 0
    shift = 0
    while shift <= 63:
        byte = cursor.read_byte()
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
        shift += 7
    raise ProtocolError("varint is too large")


def _zigzag_encode(value: int) -> int:
    return value << 1 if value >= 0 else ((-value) << 1) - 1


def _zigzag_decode(value: int) -> int:
    return value >> 1 if value & 1 == 0 else -((value >> 1) + 1)


def encode_value(value: Any, *, is_key: bool = False) -> bytes:
    """Encode one protocol value."""
    if value is None:
        return b"\x00"
    if value is True:
        return b"\x02"
    if value is False:
        return b"\x03"
    if isinstance(value, EnumValue):
        if not 0 <= value.code <= 255:
            raise ValueError("enum code must fit in one byte")
        return b"\x13" + bytes([value.code])
    if isinstance(value, int):
        return b"\x04" + _encode_varint(_zigzag_encode(value))
    if isinstance(value, str):
        if value.startswith("enum:"):
            enum_name = value[5:]
            enum_code = KEY_CODES.get(enum_name)
            if enum_code is None:
                try:
                    enum_code = int(enum_name)
                except ValueError:
                    enum_code = None
            if enum_code is not None and 0 <= enum_code <= 255:
                return encode_value(EnumValue(enum_code))
        if is_key and value in KEY_CODES:
            return encode_value(EnumValue(KEY_CODES[value]))
        encoded = value.encode("utf-8")
        return b"\x11" + _encode_varint(len(encoded)) + encoded
    if isinstance(value, Mapping):
        if len(value) > 255:
            raise ValueError("protocol maps are limited to 255 entries")
        parts = [b"\x12", bytes([len(value)])]
        for key, item in value.items():
            parts.append(encode_value(key, is_key=True))
            parts.append(encode_value(item))
        return b"".join(parts)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        indexed = {index: item for index, item in enumerate(value)}
        return encode_value(indexed)
    raise TypeError(f"unsupported protocol value {type(value).__name__}")


def encode_packet(parts: Sequence[Mapping[Any, Any]]) -> bytes:
    """Encode top-level maps into one uncompressed transport packet."""
    payload_parts = []
    for part in parts:
        encoded = encode_value(part)
        if not encoded.startswith(b"\x12"):
            raise TypeError("top-level packet parts must be maps")
        payload_parts.append(encoded[1:])
    payload = b"".join(payload_parts)
    return PLAIN_MAGIC + b"\x00\x00" + struct.pack(">I", len(payload)) + payload


def decode_value(
    cursor: Cursor,
    value_type: int | None = None,
    *,
    field_name: Any = None,
) -> Any:
    """Decode one protocol value."""
    if value_type is None:
        value_type = cursor.read_byte()
    if value_type == 0x00:
        return None
    if value_type == 0x02:
        return True
    if value_type == 0x03:
        return False
    if value_type == 0x04:
        return _zigzag_decode(_decode_varint(cursor))
    if value_type == 0x05:
        index = cursor.read_byte()
        return {"kind": "hex", "index": index, "value": cursor.read(8).hex()}
    if value_type == 0x06:
        index = cursor.read_byte()
        raw_value = _decode_varint(cursor)
        signed = -(raw_value >> 1) if raw_value & 1 else raw_value >> 1
        return TimestampValue(index=index, value=signed)
    if value_type == 0x11:
        size = _decode_varint(cursor)
        raw_value = cursor.read(size)
        if field_name == "uuid" and len(raw_value) == 16:
            return base64.urlsafe_b64encode(raw_value).rstrip(b"=").decode("ascii")
        if field_name == "nid":
            try:
                text_value = raw_value.decode("utf-8")
            except UnicodeDecodeError:
                return raw_value.hex()
            return text_value if text_value.isprintable() else raw_value.hex()
        # Some hub/firmware combinations use the protocol string type for
        # opaque or legacy-encoded bytes. Replacement decoding preserves the
        # declared field boundary so the remainder of the packet can still be
        # verified and decoded.
        return raw_value.decode("utf-8", errors="replace")
    if value_type == 0x12:
        count = cursor.read_byte()
        result: dict[Any, Any] = {}
        for _ in range(count):
            key = _map_key(decode_value(cursor))
            if key in result:
                raise ProtocolError(f"duplicate map key {key!r}")
            result[key] = decode_value(cursor, field_name=key)
        return result
    if value_type == 0x13:
        return EnumValue(cursor.read_byte())
    raise ProtocolError(f"unsupported value type 0x{value_type:02x}")


def _map_key(value: Any) -> Any:
    if isinstance(value, EnumValue):
        return value.name or f"enum:{value.code}"
    if isinstance(value, (str, int, float, bool)):
        return value
    raise ProtocolError(f"unsupported map key {value!r}")


def decode_payload(payload: bytes) -> list[dict[Any, Any]]:
    """Decode all implicit top-level maps from a transport payload."""
    cursor = Cursor(payload)
    result = []
    while cursor.remaining:
        value = decode_value(cursor, 0x12)
        if not isinstance(value, dict):
            raise ProtocolError("top-level value is not a map")
        result.append(value)
    return result


def build_login_packet(
    username: str,
    password: str,
    *,
    login_node: str,
    client_version: str,
) -> bytes:
    """Create the read-only authentication request."""
    return encode_packet(
        [
            {"_sel": 1, "sn": 1, "req": False},
            {
                "args": {
                    "cid": str(uuid.uuid4()).upper(),
                    "cver": client_version,
                    "uid": username,
                    "nick": "Home Assistant protocol probe",
                    "cname": "Home Assistant",
                    "pwd": password,
                },
                "node": login_node,
                "act": "Login",
            },
        ]
    )


def build_config_packet(base_node: str) -> bytes:
    """Create a read-only endpoint-configuration query."""
    endpoint_fields = {
        "uuid": False,
        EnumValue(114): False,
        "ver": False,
        EnumValue(14): {"m": 1, "s": False, "_chd": 1},
        "icon": False,
        "cls": False,
        EnumValue(56): False,
        "_": "eps",
        "P_Flip": False,
        "ptzmr": False,
        EnumValue(83): False,
        "nid": False,
        "devType": False,
        "cgy": False,
        EnumValue(108): False,
        "rfic": False,
        "name": False,
        "agtid": False,
    }
    return encode_packet(
        [
            {"req": False, "timestamp": 10},
            {
                "args": {
                    EnumValue(14): {EnumValue(98): endpoint_fields},
                    EnumValue(12): {EnumValue(13): False},
                    "_chd": 1,
                },
                "node": f"{base_node}/me/ep",
                "act": EnumValue(91),
            },
        ]
    )


def build_state_packet(
    agent_node: str,
    device_id: str,
    channel: str,
    state: bool,
) -> bytes:
    """Create an explicit state-changing local endpoint command."""
    return encode_packet(
        [
            {"_sel": 1, "timestamp": 10, "req": False},
            {
                "args": {
                    "valtag": "m",
                    "val": 1 if state else 0,
                    EnumValue(53): EnumValue(22),
                    "devid": device_id,
                    "key": channel,
                    "type": 128,
                },
                "node": f"{agent_node}/ep",
                "act": "rfSetA",
            },
        ]
    )


def find_first(value: Any, key: str) -> Any:
    """Recursively find the first map value with key."""
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_first(child, key)
            if found is not MISSING:
                return found
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for child in value:
            found = find_first(child, key)
            if found is not MISSING:
                return found
    return MISSING


def _indexed_value(value: Any, index: int) -> Any:
    if isinstance(value, Mapping):
        return value.get(index, value.get(str(index), MISSING))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value[index] if len(value) > index else MISSING
    return value if isinstance(value, str) else MISSING


def extract_nodes(message: Any) -> tuple[str | None, str | None]:
    """Extract base and agent nodes from a successful login response."""
    base = _indexed_value(find_first(message, "base"), 1)
    agent = _indexed_value(find_first(message, "agt"), 1)
    return (
        base if isinstance(base, str) else None,
        agent if isinstance(agent, str) else None,
    )


def to_jsonable(value: Any) -> Any:
    """Convert decoded protocol values into safe JSON-compatible values."""
    if isinstance(value, EnumValue):
        return f"enum:{value.name or value.code}"
    if isinstance(value, TimestampValue):
        return {"kind": "timestamp", "index": value.index, "value": value.value}
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_jsonable(item) for item in value]
    return value


def classify_event(message: Any) -> str:
    """Classify one decoded push message."""
    if find_first(message, "_schg") is not MISSING:
        return "state_change"
    if find_first(message, "_sdel") is not MISSING:
        return "device_deleted"
    return "other"


def iter_values(value: Any):
    """Yield nested keys and values for diagnostic matching."""
    if isinstance(value, Mapping):
        yield value
        for key, child in value.items():
            yield key
            yield from iter_values(child)
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for child in value:
            yield from iter_values(child)
    else:
        yield value


def observe_control_event(
    message: Any,
    device_id: str,
    channel: str,
) -> bool | None | object:
    """Return the observed state, None if unknown, or MISSING if unrelated."""
    strings = [str(value) for value in iter_values(message)]
    path_fragment = f"/{device_id}/m/{channel}"
    device_seen = any(value == device_id or path_fragment in value for value in strings)
    channel_seen = any(value == channel or path_fragment in value for value in strings)
    if not device_seen or not channel_seen:
        return MISSING

    for value in iter_values(message):
        if not isinstance(value, Mapping):
            continue
        state_value = value.get("val", MISSING)
        if isinstance(state_value, bool):
            return state_value
        if isinstance(state_value, int):
            return state_value != 0
        type_value = value.get("type", MISSING)
        if isinstance(type_value, int):
            return bool(type_value & 0x01)
    return None


def print_realtime_event(
    message: Any,
    frame: Frame,
    event_number: int,
    *,
    json_mode: bool,
) -> None:
    """Print one decoded event immediately without corrupting JSON stdout."""
    output = sys.stderr if json_mode else sys.stdout
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    print(
        f"\n[{timestamp}] Push event {event_number}: "
        f"{classify_event(message)} "
        f"(frame={frame.magic}, compressed={frame.compressed}, "
        f"wire_bytes={frame.wire_size})",
        file=output,
        flush=True,
    )
    print(
        json.dumps(to_jsonable(message), indent=2, ensure_ascii=False),
        file=output,
        flush=True,
    )


async def read_frame(
    reader: asyncio.StreamReader,
    frames: FrameBuffer,
    timeout: float,
) -> Frame:
    """Read one frame with a total timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        frame = frames.pop()
        if frame is not None:
            return frame
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for a complete protocol frame")
        chunk = await asyncio.wait_for(reader.read(4096), timeout=remaining)
        if not chunk:
            raise ConnectionError("hub closed the TCP connection")
        frames.feed(chunk)


async def read_message_until(
    reader: asyncio.StreamReader,
    frames: FrameBuffer,
    timeout: float,
    predicate: Callable[[Any], bool],
) -> tuple[list[dict[Any, Any]], Frame, int]:
    """Read messages until one matches predicate."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    seen = 0
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for the expected response")
        frame = await read_frame(reader, frames, remaining)
        seen += 1
        message = decode_payload(frame.payload)
        if predicate(message):
            return message, frame, seen


def summarize_devices(eps: Any, include_devices: bool) -> dict[str, Any]:
    """Return privacy-conscious configuration summary information."""
    if not isinstance(eps, Mapping):
        return {"count": 0, "types": {}, "warning": "eps was not a map"}

    types: Counter[str] = Counter()
    devices = []
    for device_id, device in eps.items():
        if not isinstance(device, Mapping):
            continue
        device_type = str(device.get("cls", "unknown"))
        types[device_type] += 1
        if include_devices:
            devices.append(
                {
                    "id": str(device_id),
                    "name": str(device.get("name", "")),
                    "type": device_type,
                    "channels": extract_channels(device),
                }
            )

    summary: dict[str, Any] = {
        "count": len(eps),
        "types": dict(sorted(types.items())),
    }
    if include_devices:
        summary["devices"] = devices
    return summary


def extract_channels(device: Mapping[Any, Any]) -> list[str]:
    """Extract endpoint channel names from a discovered device."""
    children = device.get("_chd")
    if not isinstance(children, Mapping):
        return []
    main = children.get("m")
    if not isinstance(main, Mapping):
        return []
    channels = main.get("_chd")
    if not isinstance(channels, Mapping):
        return []
    return sorted(str(channel) for channel in channels)


def find_device(eps: Any, device_id: str) -> Mapping[Any, Any] | None:
    """Find one discovered device by its endpoint identifier."""
    if not isinstance(eps, Mapping):
        return None
    for found_id, device in eps.items():
        if str(found_id) == device_id and isinstance(device, Mapping):
            return device
    return None


async def confirm_control(
    device_id: str,
    channel: str,
    state: bool,
    assume_yes: bool,
) -> None:
    """Require explicit confirmation before a state-changing command."""
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise ProbeError("control confirmation requires a TTY or --yes")
    state_name = "ON" if state else "OFF"
    prompt = f"Set {device_id}/{channel} to {state_name}? [y/N] "
    answer = await asyncio.to_thread(input, prompt)
    if answer.strip().lower() not in {"y", "yes"}:
        raise ProbeError("control command cancelled")


async def wait_for_control_event(
    reader: asyncio.StreamReader,
    frames: FrameBuffer,
    timeout: float,
    device_id: str,
    channel: str,
    *,
    show_events: bool,
    json_mode: bool,
) -> tuple[bool | None, Frame, list[dict[Any, Any]], int]:
    """Wait for a push event concerning the controlled endpoint."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    seen = 0
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for control confirmation")
        frame = await read_frame(reader, frames, remaining)
        message = decode_payload(frame.payload)
        seen += 1
        if show_events:
            print_realtime_event(message, frame, seen, json_mode=json_mode)
        observed = observe_control_event(message, device_id, channel)
        if observed is not MISSING:
            return observed, frame, message, seen


async def run_probe(args: argparse.Namespace, password: str) -> dict[str, Any]:
    """Run authentication, configuration query, and optional event listening."""
    report: dict[str, Any] = {
        "host": args.host,
        "port": args.port,
        "status": "started",
        "read_only": args.set_state is None,
    }
    frames = FrameBuffer(args.max_frame)
    started = time.monotonic()

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(args.host, args.port),
            timeout=args.timeout,
        )
    except (OSError, TimeoutError) as err:
        raise ProbeError(f"TCP connection failed: {err}") from err

    try:
        eps: Any = MISSING
        login_packet = build_login_packet(
            args.username,
            password,
            login_node=args.login_node,
            client_version=args.client_version,
        )
        writer.write(login_packet)
        await asyncio.wait_for(writer.drain(), timeout=args.timeout)

        login_message, login_frame, login_seen = await read_message_until(
            reader,
            frames,
            args.timeout,
            lambda message: find_first(message, "ret") is not MISSING
            or find_first(message, "err") is not MISSING,
        )
        login_result = find_first(login_message, "ret")
        if login_result is MISSING or login_result is None:
            error = find_first(login_message, "err")
            raise ProbeError(
                "hub rejected authentication"
                if error is MISSING
                else f"hub rejected authentication: {to_jsonable(error)}"
            )

        base_node, agent_node = extract_nodes(login_message)
        report["login"] = {
            "ok": True,
            "response_frames": login_seen,
            "frame": login_frame.magic,
            "compressed": login_frame.compressed,
            "base_node_found": base_node is not None,
            "agent_node_found": agent_node is not None,
        }
        if args.show_messages:
            report["login"]["message"] = to_jsonable(login_message)

        if not args.no_config:
            if base_node is None:
                raise ProbeError(
                    "login succeeded, but the base node was not found in the response"
                )
            writer.write(build_config_packet(base_node))
            await asyncio.wait_for(writer.drain(), timeout=args.timeout)
            config_message, config_frame, config_seen = await read_message_until(
                reader,
                frames,
                args.timeout,
                lambda message: find_first(message, "eps") is not MISSING,
            )
            eps = find_first(config_message, "eps")
            report["configuration"] = {
                "ok": True,
                "response_frames": config_seen,
                "frame": config_frame.magic,
                "compressed": config_frame.compressed,
                **summarize_devices(eps, args.show_devices),
            }
            if args.show_messages:
                report["configuration"]["message"] = to_jsonable(config_message)

        if args.set_state is not None:
            device_id, channel, requested_state = args.set_state
            desired_state = requested_state == "on"
            if agent_node is None:
                raise ProbeError(
                    "login succeeded, but the agent node required for control "
                    "was not found"
                )
            device = find_device(eps, device_id)
            if device is None:
                raise ProbeError(
                    f"device {device_id!r} was not found; use --show-devices"
                )
            device_type = str(device.get("cls", "unknown"))
            if device_type.startswith(BLOCKED_CONTROL_TYPE_PREFIXES):
                raise ProbeError(
                    f"control is intentionally blocked for lock device {device_type}"
                )
            channels = extract_channels(device)
            if channels and channel not in channels:
                raise ProbeError(
                    f"channel {channel!r} was not found on {device_id}; "
                    f"available channels: {', '.join(channels)}"
                )

            await confirm_control(
                device_id,
                channel,
                desired_state,
                args.yes,
            )
            writer.write(
                build_state_packet(
                    agent_node,
                    device_id,
                    channel,
                    desired_state,
                )
            )
            await asyncio.wait_for(writer.drain(), timeout=args.timeout)
            try:
                observed, control_frame, control_message, control_seen = (
                    await wait_for_control_event(
                        reader,
                        frames,
                        args.control_timeout,
                        device_id,
                        channel,
                        show_events=args.show_events,
                        json_mode=args.json,
                    )
                )
            except TimeoutError as err:
                raise ProbeError(
                    "control command was sent, but no matching push event was "
                    "observed"
                ) from err
            report["control"] = {
                "device_id": device_id,
                "device_type": device_type,
                "channel": channel,
                "requested_state": requested_state,
                "observed_state": (
                    None if observed is None else "on" if observed else "off"
                ),
                "state_confirmed": observed is desired_state,
                "response_frames": control_seen,
                "frame": control_frame.magic,
                "compressed": control_frame.compressed,
            }
            if args.show_messages:
                report["control"]["message"] = to_jsonable(control_message)
            if observed is not None and observed is not desired_state:
                raise ProbeError(
                    "a matching push event reported the opposite state"
                )

        if args.listen > 0:
            events = Counter()
            event_frames = 0
            listen_deadline = asyncio.get_running_loop().time() + args.listen
            while True:
                remaining = listen_deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    frame = await read_frame(reader, frames, remaining)
                except TimeoutError:
                    break
                message = decode_payload(frame.payload)
                event_frames += 1
                event_type = classify_event(message)
                events[event_type] += 1
                if args.show_events:
                    print_realtime_event(
                        message,
                        frame,
                        event_frames,
                        json_mode=args.json,
                    )
            report["events"] = {
                "listen_seconds": args.listen,
                "frames": event_frames,
                "types": dict(events),
            }

        report["status"] = "verified"
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return report
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify LifeSmart LAN authentication, packet decoding, and read-only "
            "device discovery. No device-control command is sent."
        )
    )
    parser.add_argument("--host", required=True, help="LifeSmart hub IP or hostname")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--password",
        default=None,
        help=(
            "Hub password. Prefer the interactive prompt or "
            "LIFESMART_LOCAL_PASSWORD environment variable."
        ),
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--listen",
        type=float,
        default=0,
        metavar="SECONDS",
        help="After discovery, listen for push events for this many seconds",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Verify authentication only; do not request device configuration",
    )
    parser.add_argument(
        "--show-devices",
        action="store_true",
        help="Include device IDs and names in output (privacy-sensitive)",
    )
    parser.add_argument(
        "--show-messages",
        action="store_true",
        help="Include decoded responses in output (very privacy-sensitive)",
    )
    parser.add_argument(
        "--show-events",
        action="store_true",
        help=(
            "Print each decoded push event immediately "
            "(privacy-sensitive; requires --listen)"
        ),
    )
    parser.add_argument(
        "--set-state",
        nargs=3,
        metavar=("DEVICE_ID", "CHANNEL", "STATE"),
        help="Set one endpoint channel state; STATE must be on or off",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation for --set-state",
    )
    parser.add_argument(
        "--control-timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Seconds to wait for a matching push confirmation",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show a traceback for unexpected verifier errors",
    )
    parser.add_argument(
        "--max-frame",
        type=int,
        default=DEFAULT_MAX_FRAME,
        help="Maximum accepted encoded or expanded frame size",
    )
    parser.add_argument(
        "--login-node",
        default="homeassistant",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--client-version", default="1.0.48p1", help=argparse.SUPPRESS
    )
    return parser


def print_human_report(report: Mapping[str, Any]) -> None:
    """Print the concise default report."""
    print(f"Connected to {report['host']}:{report['port']}")
    login = report.get("login", {})
    print(
        "Authentication: OK "
        f"({login.get('frame')}, compressed={login.get('compressed')})"
    )
    if "configuration" in report:
        config = report["configuration"]
        print(
            "Configuration: OK "
            f"({config.get('frame')}, compressed={config.get('compressed')})"
        )
        print(f"Devices found: {config.get('count', 0)}")
        if config.get("types"):
            print("Device types:")
            for device_type, count in config["types"].items():
                print(f"  {device_type}: {count}")
        if config.get("devices"):
            print("Devices:")
            for device in config["devices"]:
                channels = ",".join(device.get("channels", [])) or "unknown"
                print(
                    f"  {device['id']}  {device['type']}  {device['name']} "
                    f"channels={channels}"
                )
    if "events" in report:
        events = report["events"]
        print(
            f"Push events: {events['frames']} frame(s) in "
            f"{events['listen_seconds']} second(s)"
        )
    if "control" in report:
        control = report["control"]
        print(
            "Control: "
            f"{control['device_id']}/{control['channel']} -> "
            f"{control['requested_state'].upper()}, "
            f"observed={control['observed_state']}, "
            f"confirmed={control['state_confirmed']}"
        )
    print(f"Protocol verification: {report['status'].upper()}")


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    if (
        args.timeout <= 0
        or args.control_timeout <= 0
        or args.listen < 0
        or args.max_frame <= 0
    ):
        parser.error("timeout/max-frame must be positive and listen cannot be negative")
    if args.show_events and args.listen <= 0:
        if args.set_state is None:
            parser.error(
                "--show-events requires --listen or --set-state"
            )
    if args.set_state is not None:
        args.set_state[2] = args.set_state[2].lower()
        if args.set_state[2] not in {"on", "off"}:
            parser.error("--set-state STATE must be 'on' or 'off'")
        if args.no_config:
            parser.error("--set-state cannot be combined with --no-config")
    elif args.yes:
        parser.error("--yes requires --set-state")

    password = args.password
    if password is None:
        password = os.environ.get("LIFESMART_LOCAL_PASSWORD")
    if password is None:
        if not sys.stdin.isatty():
            print(
                "Error: password required via interactive prompt, --password, or "
                "LIFESMART_LOCAL_PASSWORD",
                file=sys.stderr,
            )
            return 2
        password = getpass.getpass("LifeSmart hub password: ")

    try:
        report = asyncio.run(run_probe(args, password))
    except (ProbeError, ProtocolError, TimeoutError, ConnectionError) as err:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(err)}, indent=2))
        else:
            print(f"Protocol verification failed: {err}", file=sys.stderr)
        return 1
    except Exception as err:  # noqa: BLE001
        if args.debug:
            raise
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": f"{type(err).__name__}: {err}",
                    },
                    indent=2,
                )
            )
        else:
            print(
                "Protocol verification failed with an unexpected decoder "
                f"error: {type(err).__name__}: {err}",
                file=sys.stderr,
            )
            print("Re-run with --debug to show the traceback.", file=sys.stderr)
        return 1

    if args.json or args.show_messages:
        print(json.dumps(to_jsonable(report), indent=2, ensure_ascii=False))
    else:
        print_human_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
