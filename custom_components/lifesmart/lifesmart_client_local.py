"""LifeSmart local hub protocol client.

The wire format and requests in this module are based on the repository's
``scripts/verify_local_protocol.py`` protocol verifier.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
import logging
import re
import struct
from typing import Any
import uuid
import zlib

from .const import (
    DEVICE_DATA_KEY,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    HUB_ID_KEY,
)

_LOGGER = logging.getLogger(__name__)

PLAIN_MAGIC = b"GL00"
GZIP_MAGIC = b"ZZ00"
GZIP_STREAM_MAGIC = b"\x1f\x8b"
HEADER_SIZE = 10
DEFAULT_LOCAL_PORT = 8888
DEFAULT_LOCAL_PASSWORD = "admin"
DEFAULT_TIMEOUT = 5.0
RECONNECT_DELAY = 10.0
DEFAULT_MAX_FRAME = 8 * 1024 * 1024
LOGIN_NODE = "A3MAAABaAEkBRzQ0Mzc0OA/ac"
CLIENT_VERSION = "1.0.48p1"

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
    41: "val",
    42: "ver",
    46: "cgy",
    47: "key",
    53: "response_token",
    78: "type",
    89: "icon",
    90: "uuid",
    106: "_chd",
    113: "agtid",
}
KEY_CODES = {name: code for code, name in KEY_NAMES.items()}
MISSING = object()

# These suffixes identify distinct device families in the cloud API and must
# not be mistaken for the local protocol/firmware suffix appended to classes.
VERSIONED_DEVICE_TYPES = {
    "SL_DOOYA_V2",
    "SL_DOOYA_V3",
    "SL_DOOYA_V4",
    "SL_P_IR_V2",
    "SL_P_V2",
}

LOCAL_SCENE_CLASSES = {"scene", "groupirc"}


class LocalProtocolError(RuntimeError):
    """The local hub returned malformed or unsupported protocol data."""


@dataclass(frozen=True, slots=True)
class EnumValue:
    """A numeric enum in the LifeSmart binary encoding."""

    code: int

    @property
    def name(self) -> str | None:
        """Return the known symbolic name."""
        return KEY_NAMES.get(self.code)


class Cursor:
    """Bounds-checked packet reader."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    @property
    def remaining(self) -> int:
        """Return the unread byte count."""
        return len(self.data) - self.pos

    def read(self, size: int) -> bytes:
        """Read exactly size bytes."""
        if size < 0 or self.pos + size > len(self.data):
            raise LocalProtocolError(f"truncated value at offset {self.pos}")
        value = self.data[self.pos : self.pos + size]
        self.pos += size
        return value

    def read_byte(self) -> int:
        """Read one byte."""
        return self.read(1)[0]


class FrameBuffer:
    """Incrementally extract plain and gzip-compressed frames."""

    def __init__(self, max_frame: int = DEFAULT_MAX_FRAME) -> None:
        self.max_frame = max_frame
        self._buffer = bytearray()

    def feed(self, data: bytes) -> None:
        """Append received bytes."""
        self._buffer.extend(data)
        if len(self._buffer) > self.max_frame * 2 + HEADER_SIZE:
            raise LocalProtocolError("wire buffer exceeded its safety limit")

    def pop(self) -> bytes | None:
        """Return a decoded frame payload when complete."""
        if len(self._buffer) < 4:
            return None
        magic = bytes(self._buffer[:4])
        if magic == PLAIN_MAGIC:
            return self._pop_plain()
        if magic == GZIP_MAGIC:
            return self._pop_gzip()
        raise LocalProtocolError(f"unexpected frame magic {magic!r}")

    def _pop_plain(self) -> bytes | None:
        if len(self._buffer) < HEADER_SIZE:
            return None
        size = struct.unpack(">I", self._buffer[6:10])[0]
        if size > self.max_frame:
            raise LocalProtocolError("declared frame exceeds safety limit")
        end = HEADER_SIZE + size
        if len(self._buffer) < end:
            return None
        payload = bytes(self._buffer[HEADER_SIZE:end])
        del self._buffer[:end]
        return payload

    def _pop_gzip(self) -> bytes | None:
        if len(self._buffer) >= 12 and self._buffer[10:12] == GZIP_STREAM_MAGIC:
            offset, size = 10, struct.unpack(">I", self._buffer[6:10])[0]
        elif len(self._buffer) >= 10 and self._buffer[8:10] == GZIP_STREAM_MAGIC:
            offset, size = 8, struct.unpack(">I", self._buffer[4:8])[0]
        elif len(self._buffer) < 12:
            return None
        else:
            raise LocalProtocolError("compressed frame has no gzip stream")
        if size > self.max_frame:
            raise LocalProtocolError("declared expanded frame exceeds safety limit")
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            expanded = decoder.decompress(
                bytes(self._buffer[offset:]), self.max_frame + 1
            )
        except zlib.error as err:
            raise LocalProtocolError(f"invalid gzip frame: {err}") from err
        if len(expanded) > self.max_frame or decoder.unconsumed_tail:
            raise LocalProtocolError("expanded frame exceeded its safety limit")
        if not decoder.eof:
            return None
        expanded += decoder.flush()
        if len(expanded) != size:
            raise LocalProtocolError("compressed frame size mismatch")
        wire_size = (
            offset + len(bytes(self._buffer[offset:])) - len(decoder.unused_data)
        )
        del self._buffer[:wire_size]
        if expanded[:4] in (PLAIN_MAGIC, GZIP_MAGIC):
            nested = FrameBuffer(self.max_frame)
            nested.feed(expanded)
            payload = nested.pop()
            if payload is None or nested._buffer:
                raise LocalProtocolError("compressed payload is not one complete frame")
            return payload
        return expanded


def _encode_varint(value: int) -> bytes:
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def _decode_varint(cursor: Cursor) -> int:
    value = 0
    for shift in range(0, 64, 7):
        byte = cursor.read_byte()
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
    raise LocalProtocolError("varint is too large")


def encode_value(value: Any, *, is_key: bool = False) -> bytes:
    """Encode one protocol value."""
    if value is None:
        return b"\x00"
    if value is True:
        return b"\x02"
    if value is False:
        return b"\x03"
    if isinstance(value, EnumValue):
        return b"\x13" + bytes([value.code])
    if isinstance(value, int):
        zigzag = value << 1 if value >= 0 else ((-value) << 1) - 1
        return b"\x04" + _encode_varint(zigzag)
    if isinstance(value, str):
        if is_key and value in KEY_CODES:
            return encode_value(EnumValue(KEY_CODES[value]))
        encoded = value.encode()
        return b"\x11" + _encode_varint(len(encoded)) + encoded
    if isinstance(value, Mapping):
        if len(value) > 255:
            raise ValueError("protocol maps are limited to 255 entries")
        parts = [b"\x12", bytes([len(value)])]
        for key, item in value.items():
            parts.extend((encode_value(key, is_key=True), encode_value(item)))
        return b"".join(parts)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return encode_value(dict(enumerate(value)))
    raise TypeError(f"unsupported protocol value {type(value).__name__}")


def decode_value(
    cursor: Cursor,
    value_type: int | None = None,
    *,
    field_name: Any = None,
) -> Any:
    """Decode one protocol value."""
    value_type = cursor.read_byte() if value_type is None else value_type
    if value_type == 0x00:
        return None
    if value_type == 0x02:
        return True
    if value_type == 0x03:
        return False
    if value_type == 0x04:
        value = _decode_varint(cursor)
        return value >> 1 if value & 1 == 0 else -((value >> 1) + 1)
    if value_type == 0x05:
        index = cursor.read_byte()
        return {"kind": "hex", "index": index, "value": cursor.read(8).hex()}
    if value_type == 0x06:
        index = cursor.read_byte()
        value = _decode_varint(cursor)
        return {
            "kind": "timestamp",
            "index": index,
            "value": -(value >> 1) if value & 1 else value >> 1,
        }
    if value_type == 0x11:
        raw_value = cursor.read(_decode_varint(cursor))
        if field_name == "uuid" and len(raw_value) == 16:
            return base64.urlsafe_b64encode(raw_value).rstrip(b"=").decode("ascii")
        if field_name == "nid":
            try:
                text_value = raw_value.decode()
            except UnicodeDecodeError:
                return raw_value.hex()
            return text_value if text_value.isprintable() else raw_value.hex()
        return raw_value.decode(errors="replace")
    if value_type == 0x12:
        result = {}
        for _ in range(cursor.read_byte()):
            key = decode_value(cursor)
            if isinstance(key, EnumValue):
                key = key.name or f"enum:{key.code}"
            if not isinstance(key, (str, int, float, bool)):
                raise LocalProtocolError(f"unsupported map key {key!r}")
            result[key] = decode_value(cursor, field_name=key)
        return result
    if value_type == 0x13:
        return EnumValue(cursor.read_byte())
    raise LocalProtocolError(f"unsupported value type 0x{value_type:02x}")


def encode_packet(parts: Sequence[Mapping[Any, Any]]) -> bytes:
    """Encode top-level maps into one transport packet."""
    payload = b"".join(encode_value(part)[1:] for part in parts)
    return PLAIN_MAGIC + b"\x00\x00" + struct.pack(">I", len(payload)) + payload


def decode_payload(payload: bytes) -> list[dict[Any, Any]]:
    """Decode all implicit top-level maps in a frame."""
    cursor = Cursor(payload)
    result = []
    while cursor.remaining:
        result.append(decode_value(cursor, 0x12))
    return result


def find_first(value: Any, key: str) -> Any:
    """Recursively find a map value."""
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_first(child, key)
            if found is not MISSING:
                return found
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            found = find_first(child, key)
            if found is not MISSING:
                return found
    return MISSING


def _indexed(value: Any, index: int) -> Any:
    if isinstance(value, Mapping):
        return value.get(index, value.get(str(index), MISSING))
    return value


def build_login_packet(password: str) -> bytes:
    """Create a local authentication request."""
    return encode_packet(
        [
            {"_sel": 1, "sn": 1, "req": False},
            {
                "args": {
                    "cid": str(uuid.uuid4()).upper(),
                    "cver": CLIENT_VERSION,
                    "uid": "admin",
                    "nick": "Home Assistant",
                    "cname": "Home Assistant",
                    "pwd": password,
                },
                "node": LOGIN_NODE,
                "act": "Login",
            },
        ]
    )


def build_config_packet(base_node: str) -> bytes:
    """Create the endpoint configuration query verified by the probe."""
    fields = {
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
                    EnumValue(14): {EnumValue(98): fields},
                    EnumValue(12): {EnumValue(13): False},
                    "_chd": 1,
                },
                "node": f"{base_node}/me/ep",
                "act": EnumValue(91),
            },
        ]
    )


def build_control_packet(
    agent_node: str, device_id: str, channel: str, value: Any, value_type: int
) -> bytes:
    """Create a local endpoint state command."""
    return encode_packet(
        [
            {"_sel": 1, "timestamp": 10, "req": False},
            {
                "args": {
                    "valtag": "m",
                    "val": value,
                    "response_token": EnumValue(22),
                    "devid": device_id,
                    "key": channel,
                    "type": value_type & 0xFE,
                },
                "node": f"{agent_node}/ep",
                "act": "rfSetA",
            },
        ]
    )


def build_scene_query_packet(agent_node: str) -> bytes:
    """Create the read-only query for locally stored hub scenes."""
    fields = {
        "cron_name": False,
        "name": False,
        "cls": False,
        "desc": False,
        "_": "ai",
        "_chd": 1,
    }
    return encode_packet(
        [
            {"req": False, "timestamp": 10},
            {
                "args": {
                    EnumValue(14): {EnumValue(98): fields},
                    EnumValue(12): {EnumValue(13): False},
                    "_chd": 1,
                },
                "node": f"{agent_node}/ai",
                "act": EnumValue(91),
            },
        ]
    )


def build_scene_run_packet(agent_node: str, scene_id: str) -> bytes:
    """Create the verified RunA request for one locally stored scene."""
    return encode_packet(
        [
            {"_sel": 1, "timestamp": 10, "req": False},
            {
                "args": {"cron_name": scene_id},
                "node": f"{agent_node}/ai",
                "act": "RunA",
            },
        ]
    )


class LocalLifeSmartClient:
    """Persistent client for one LifeSmart hub on the local network."""

    is_local = True

    def __init__(
        self, host: str, port: int, password: str, *, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._frames = FrameBuffer()
        self._base_node: str | None = None
        self._agent_node: str | None = None
        self._hub_id = host
        self._devices: list[dict[str, Any]] = []
        self._scenes: list[dict[str, str]] = []
        self._scene_ids: set[str] = set()
        self._listener_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()

    @property
    def hub_id(self) -> str:
        """Return the stable hub identifier learned during authentication."""
        return self._hub_id

    async def _read_frame(self) -> list[dict[Any, Any]]:
        if self._reader is None:
            raise ConnectionError("local hub is not connected")
        while (payload := self._frames.pop()) is None:
            chunk = await self._reader.read(4096)
            if not chunk:
                raise ConnectionError("hub closed the local connection")
            self._frames.feed(chunk)
        message = decode_payload(payload)
        _LOGGER.debug(
            "LifeSmart local decoded response/event from %s:%s: %s",
            self.host,
            self.port,
            message,
        )
        return message

    async def _read_until(self, predicate: Callable[[Any], bool]) -> Any:
        async with asyncio.timeout(self.timeout):
            while True:
                message = await self._read_frame()
                if predicate(message):
                    return message

    async def _send(self, packet: bytes) -> None:
        if self._writer is None:
            raise ConnectionError("local hub is not connected")
        async with self._write_lock:
            self._writer.write(packet)
            await asyncio.wait_for(self._writer.drain(), self.timeout)

    async def login_async(self) -> dict[str, Any]:
        """Connect and authenticate with the hub."""
        if self._writer is None:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        await self._send(build_login_packet(self.password))
        message = await self._read_until(
            lambda msg: (
                find_first(msg, "ret") is not MISSING
                or find_first(msg, "err") is not MISSING
            )
        )
        result = find_first(message, "ret")
        if result is MISSING or result is None:
            return {"code": "failure", "message": "invalid local hub password"}
        nodes = find_first(message, "base"), find_first(message, "agt")
        base, agent = _indexed(nodes[0], 1), _indexed(nodes[1], 1)
        if not isinstance(base, str) or not isinstance(agent, str):
            raise LocalProtocolError("login response did not include hub nodes")
        self._base_node, self._agent_node = base, agent
        agent_root = agent.rstrip("/")
        if agent_root.endswith("/me"):
            agent_root = agent_root[: -len("/me")].rstrip("/")
        self._hub_id = agent_root.rsplit("/", 1)[-1] or self.host
        return {"code": "success"}

    async def get_all_device_async(self) -> list[dict[str, Any]]:
        """Discover and normalize all local endpoints."""
        if self._base_node is None:
            raise ConnectionError("local hub is not authenticated")
        await self._send(build_config_packet(self._base_node))
        message = await self._read_until(
            lambda msg: find_first(msg, "eps") is not MISSING
        )
        eps = find_first(message, "eps")
        self._devices = self._normalize_devices(eps)
        return [dict(device) for device in self._devices]

    def _normalize_devices(self, eps: Any) -> list[dict[str, Any]]:
        devices = []
        if not isinstance(eps, Mapping):
            return devices
        for raw_id, raw in eps.items():
            if not isinstance(raw, Mapping):
                continue
            device_id = str(raw_id)
            device_type = raw.get("cls") or raw.get("devType")
            if not isinstance(device_type, str) or not device_type:
                continue
            device_type = self._normalize_device_type(device_type)
            hub_id = raw.get("agtid")
            if not isinstance(hub_id, str) or not hub_id or hub_id.lower() == "all":
                hub_id = self._hub_id
            self._hub_id = hub_id
            children = raw.get("_chd", {})
            main = children.get("m", {}) if isinstance(children, Mapping) else {}
            channels = main.get("_chd", {}) if isinstance(main, Mapping) else {}
            data = {}
            if isinstance(channels, Mapping):
                for channel, channel_data in channels.items():
                    normalized = (
                        dict(channel_data)
                        if isinstance(channel_data, Mapping)
                        else {"val": channel_data}
                    )
                    normalized.setdefault("name", str(channel))
                    normalized["type"] = self._simple_value(normalized.get("type", 0))
                    if "val" in normalized:
                        normalized["val"] = self._simple_value(normalized["val"])
                    data[str(channel)] = normalized
            devices.append(
                {
                    DEVICE_ID_KEY: device_id,
                    HUB_ID_KEY: hub_id,
                    DEVICE_TYPE_KEY: device_type,
                    DEVICE_NAME_KEY: str(raw.get("name") or device_id),
                    "ver": str(raw.get("ver") or ""),
                    "stat": 1,
                    DEVICE_DATA_KEY: data,
                }
            )
        return devices

    @staticmethod
    def _simple_value(value: Any) -> Any:
        if isinstance(value, EnumValue):
            return value.code
        if (
            isinstance(value, Mapping)
            and value.get("kind") in ("timestamp", "hex")
            and "value" in value
        ):
            return value["value"]
        return value

    @staticmethod
    def _normalize_device_type(device_type: str) -> str:
        """Remove a local class-version suffix while preserving real variants."""
        if device_type in VERSIONED_DEVICE_TYPES:
            return device_type
        return re.sub(r"_V\d+$", "", device_type)

    async def get_all_hubs_async(self) -> list[dict[str, Any]]:
        """Return metadata for this locally connected hub."""
        return [
            {
                HUB_ID_KEY: self._hub_id,
                "name": "LifeSmart Hub",
                "ip": self.host,
                "stat": 1,
            }
        ]

    async def get_hub_state_async(self, _hub_id: str) -> dict[str, Any]:
        return {"state": 2 if self._writer is not None else 0}

    async def get_hub_system_info_async(self, _hub_id: str) -> dict[str, Any]:
        return {"ip": self.host}

    async def get_hub_timezone_async(self, _hub_id: str) -> dict[str, Any]:
        return {}

    async def get_all_scene_async(self, _hub_id: str) -> list[dict[str, str]]:
        """Discover scenes stored on the locally connected hub."""
        if self._agent_node is None:
            raise ConnectionError("local hub is not authenticated")
        await self._send(build_scene_query_packet(self._agent_node))
        message = await self._read_until(
            lambda msg: (
                find_first(msg, "ai") is not MISSING
                or find_first(msg, "err") is not MISSING
            )
        )
        ai = find_first(message, "ai")
        if ai is MISSING:
            error = find_first(message, "err")
            raise LocalProtocolError(
                "local scene discovery was rejected"
                if error is MISSING
                else f"local scene discovery was rejected: {error}"
            )
        self._scenes = self._normalize_scenes(ai)
        self._scene_ids = {scene["id"] for scene in self._scenes}
        return [dict(scene) for scene in self._scenes]

    @staticmethod
    def _normalize_scenes(ai: Any) -> list[dict[str, str]]:
        """Normalize executable scene records from the hub's AI object tree."""
        if not isinstance(ai, Mapping):
            return []
        scenes = []
        for raw_id, raw_scene in ai.items():
            if not isinstance(raw_scene, Mapping):
                continue
            scene_class = raw_scene.get("cls")
            if scene_class not in LOCAL_SCENE_CLASSES:
                continue
            scene_id = str(raw_scene.get("cron_name") or raw_id).strip()
            if not scene_id:
                continue
            raw_name = raw_scene.get("name")
            scene_name = str(raw_name).strip() if raw_name is not None else ""
            scenes.append(
                {
                    "id": scene_id,
                    "name": scene_name or f"LifeSmart Scene {scene_id}",
                }
            )
        return scenes

    async def set_scene_async(self, hub_id: str, scene_id: str) -> int | dict[str, Any]:
        """Activate a discovered local scene through the hub's RunA action."""
        if self._agent_node is None:
            raise ConnectionError("local hub is not authenticated")
        if hub_id != self._hub_id or scene_id not in self._scene_ids:
            return {"code": "failure", "message": "unknown local scene"}
        await self._send(build_scene_run_packet(self._agent_node, scene_id))
        # The listener owns the TCP reader after setup. Match endpoint control
        # semantics and report successful dispatch without racing it for the ack.
        return 0

    async def turn_on_light_swith_async(self, idx: str, agt: str, me: str) -> int:
        """Turn on a switch-compatible local endpoint."""
        return await self.send_epset_async("0x81", 1, idx, agt, me)

    async def turn_off_light_swith_async(self, idx: str, agt: str, me: str) -> int:
        """Turn off a switch-compatible local endpoint."""
        return await self.send_epset_async("0x80", 0, idx, agt, me)

    async def send_epset_async(
        self, type: str, val: Any, idx: str, _agt: str, me: str
    ) -> int:
        """Send a local endpoint command."""
        if self._agent_node is None:
            raise ConnectionError("local hub is not authenticated")
        value_type = int(str(type), 0)
        await self._send(
            build_control_packet(self._agent_node, me, idx, val, value_type)
        )
        return 0

    async def get_epget_async(self, agt: str, me: str) -> dict[str, Any]:
        """Return the most recently discovered local endpoint data."""
        for device in self._devices:
            if device[HUB_ID_KEY] == agt and device[DEVICE_ID_KEY] == me:
                return dict(device[DEVICE_DATA_KEY])
        return {}

    def start_listener(
        self,
        on_event: Callable[[dict[str, Any]], None],
        on_connection: Callable[[bool, str | None], None],
    ) -> None:
        """Start processing local push messages."""
        if self._listener_task is None:
            self._listener_task = asyncio.create_task(
                self._listen(on_event, on_connection),
                name="LifeSmart local push listener",
            )
            on_connection(True, None)

    async def _listen(
        self,
        on_event: Callable[[dict[str, Any]], None],
        on_connection: Callable[[bool, str | None], None],
    ) -> None:
        while True:
            try:
                message = await self._read_frame()
                for event in self._cloud_events_from_message(message):
                    _LOGGER.debug("LifeSmart local normalized push event: %s", event)
                    on_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("LifeSmart local connection lost: %s", err)
                if self._writer is not None:
                    self._writer.close()
                self._reader = self._writer = None
                self._frames = FrameBuffer()
                on_connection(False, type(err).__name__)
                while self._writer is None:
                    await asyncio.sleep(RECONNECT_DELAY)
                    try:
                        response = await self.login_async()
                        if response.get("code") != "success":
                            raise PermissionError("hub rejected local credentials")
                        await self.get_all_device_async()
                    except asyncio.CancelledError:
                        raise
                    except Exception as reconnect_err:  # noqa: BLE001
                        _LOGGER.debug(
                            "Unable to reconnect to LifeSmart hub: %s",
                            reconnect_err,
                        )
                        if self._writer is not None:
                            self._writer.close()
                        self._reader = self._writer = None
                        self._frames = FrameBuffer()
                    else:
                        on_connection(True, None)

    def _cloud_events_from_message(self, message: Any) -> list[dict[str, Any]]:
        """Convert local changes to the same envelope as cloud WebSocket events."""
        return [
            {"type": "io", "msg": event} for event in self._events_from_message(message)
        ]

    def _events_from_message(self, message: Any) -> list[dict[str, Any]]:
        changes = find_first(message, "_schg")
        if not isinstance(changes, Mapping):
            return []
        events = []
        for path, raw_change in changes.items():
            parts = str(path).rstrip("/").split("/")
            if "m" not in parts:
                continue
            marker = len(parts) - 1 - parts[::-1].index("m")
            if marker < 1 or marker + 1 >= len(parts):
                continue
            device_id, channel = parts[marker - 1], parts[marker + 1]
            device = next(
                (item for item in self._devices if item[DEVICE_ID_KEY] == device_id),
                None,
            )
            if device is None:
                continue
            change = find_first(raw_change, "chg")
            if not isinstance(change, Mapping):
                change = raw_change if isinstance(raw_change, Mapping) else {}
            if "type" not in change and "val" not in change:
                # Heartbeat notifications can touch a channel timestamp without
                # changing its state. Do not turn that into a false entity update.
                continue
            event = {
                DEVICE_TYPE_KEY: device[DEVICE_TYPE_KEY],
                HUB_ID_KEY: device[HUB_ID_KEY],
                DEVICE_ID_KEY: device_id,
                "idx": channel,
            }
            cached_state = device[DEVICE_DATA_KEY].setdefault(channel, {})
            for state_key in ("type", "val"):
                if state_key in cached_state:
                    event[state_key] = cached_state[state_key]
            normalized_change = {
                str(key): self._simple_value(value) for key, value in change.items()
            }
            event.update(normalized_change)
            cached_state.update(normalized_change)
            events.append(event)
        return events

    async def async_close(self) -> None:
        """Stop listening and close the TCP stream."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        if self._writer is not None:
            self._writer.close()
            with suppress(OSError):
                await self._writer.wait_closed()
        self._reader = self._writer = None
