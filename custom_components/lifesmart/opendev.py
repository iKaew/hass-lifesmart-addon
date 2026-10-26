"""Read documented battery percentages from an enabled local OpenDev service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import secrets
import socket
import struct
import time

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .battery import battery_percentage

CONF_OPENDEV_ENABLED = "opendev_enabled"
CONF_OPENDEV_MODEL = "opendev_model"
CONF_OPENDEV_TOKEN = "opendev_token"
OPENDEV_PORT = 12348
_LOGGER = logging.getLogger(__name__)


def encode_request(model, token, request_id, timestamp):
    """Encode the documented read-only GET eps request, without controls."""
    original = f"obj:eps,ts:{timestamp},model:{model},token:{token}"
    signature = hashlib.md5(original.encode(), usedforsecurity=False).hexdigest()
    body = json.dumps(
        {
            "sys": {"ver": 1, "sign": signature, "model": model, "ts": timestamp},
            "id": request_id,
            "obj": "eps",
            "args": {},
        }
    ).encode()
    return struct.pack(">2sHHI", b"JL", 0, 1, len(body)) + body


def decode_response(packet, request_id, hub_id):
    """Validate framing and bind a response to this request and configured hub."""
    if len(packet) < 10:
        return None
    magic, version, kind, size = struct.unpack(">2sHHI", packet[:10])
    if magic != b"JL" or version != 0 or kind != 2 or size != len(packet) - 10:
        return None
    try:
        body = json.loads(packet[10:])
    except ValueError, UnicodeError:
        return None
    if not isinstance(body, dict) or body.get("id") != request_id:
        return None
    if body.get("agtid") != hub_id:
        return None
    if body.get("code") != 0:
        raise UpdateFailed("OpenDev rejected the battery query")
    if not isinstance(body.get("msg"), list):
        raise UpdateFailed("OpenDev returned an invalid device list")
    return body["msg"]


class OpenDevClient:
    """Use an ephemeral UDP source port for QR-enabled OpenDev services."""

    def __init__(self, host, model, token, hub_id):
        self.host = host
        self.model = model
        self._token = token
        self.hub_id = hub_id

    async def async_get_devices(self):
        """Perform one bounded read; always close the socket, including cancellation."""
        loop = asyncio.get_running_loop()
        request_id = secrets.randbelow(2**31 - 1) + 1
        request = encode_request(self.model, self._token, request_id, int(time.time()))
        try:
            async with asyncio.timeout(6):
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.setblocking(False)
                    sock.bind(("0.0.0.0", 0))
                    # A connected UDP socket accepts responses only from this peer.
                    await loop.sock_connect(sock, (self.host, OPENDEV_PORT))
                    await loop.sock_sendall(sock, request)
                    while True:
                        packet = await loop.sock_recv(sock, 65535)
                        devices = decode_response(packet, request_id, self.hub_id)
                        if devices is not None:
                            return devices
        except (TimeoutError, OSError) as err:
            raise UpdateFailed("Unable to read OpenDev battery percentages") from err


def parse_batteries(devices, targets, hub_id):
    """Extract only matching, online devices with valid friendly battery values."""
    result = {}
    seen = set()
    for device in devices:
        if not isinstance(device, dict):
            continue
        device_id = device.get("me")
        if not isinstance(device_id, str) or device_id not in targets:
            continue
        if device_id in seen:
            result.pop(device_id, None)
            continue
        seen.add(device_id)
        if device.get("agt") != hub_id or device.get("devtype") != targets[device_id]:
            continue
        if device.get("stat") != 1:
            continue
        channels = device.get("data")
        channel = channels.get("V") if isinstance(channels, dict) else None
        if not isinstance(channel, dict):
            continue
        percentage = battery_percentage(channel.get("v"))
        if percentage is None:
            continue
        reported_at = None
        raw_timestamp = channel.get("valts")
        if isinstance(raw_timestamp, (int, float)) and not isinstance(
            raw_timestamp, bool
        ):
            try:
                if raw_timestamp > 0:
                    reported_at = datetime.fromtimestamp(
                        raw_timestamp / 1000, timezone.utc
                    ).isoformat()
            except OverflowError, ValueError, OSError:
                pass
        result[device_id] = {"percentage": percentage, "reported_at": reported_at}
    return result


class OpenDevBatteryCoordinator(DataUpdateCoordinator):
    """Poll only the battery observations used by existing battery entities."""

    def __init__(self, hass, entry, client, targets):
        self.client = client
        self.targets = targets
        self.last_successful_query = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="LifeSmart OpenDev battery",
            update_interval=timedelta(minutes=5),
            always_update=False,
        )

    async def _async_update_data(self):
        devices = await self.client.async_get_devices()
        observations = parse_batteries(devices, self.targets, self.client.hub_id)
        self.last_successful_query = datetime.now(timezone.utc).isoformat()
        return observations
