"""Support for LifeSmart SPOT IR remote controls."""

import asyncio
import base64
import binascii
import logging
from typing import Any

from homeassistant.components.remote import (
    ATTR_COMMAND,
    ATTR_COMMAND_TYPE,
    ATTR_DELAY_SECS,
    ATTR_DEVICE,
    ATTR_NUM_REPEATS,
    RemoteEntity,
    RemoteEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.storage import Store

from . import LifeSmartDevice, generate_entity_id
from .const import (
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DEVICE_VERSION_KEY,
    DOMAIN,
    HUB_ID_KEY,
    SPOT_TYPES,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}_spot_ir_commands"
STORAGE_VERSION = 1
DEFAULT_COMMAND_DEVICE = "__default__"
DEFAULT_COMMAND_TYPE = "ir"


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Setup remote entities."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    exclude_devices = hass.data[DOMAIN][config_entry.entry_id]["exclude_devices"]
    exclude_hubs = hass.data[DOMAIN][config_entry.entry_id]["exclude_hubs"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]
    remote_devices = []

    for device in devices:
        if (
            device[DEVICE_ID_KEY] in exclude_devices
            or device[HUB_ID_KEY] in exclude_hubs
        ):
            continue

        device_type = device[DEVICE_TYPE_KEY]
        if device_type not in SPOT_TYPES:
            continue

        # Create remote control entity for SPOT devices
        ha_device = LifeSmartDevice(device, client)
        remote_devices.append(LifeSmartSPOTRemote(ha_device, device, client))

    async_add_entities(remote_devices)


class LifeSmartSPOTRemote(RemoteEntity):
    """Representation of a LifeSmart SPOT IR remote control."""

    def __init__(self, ha_device, raw_device_data, client):
        """Initialize the remote."""
        self._device = ha_device
        self._raw_device_data = raw_device_data
        self._client = client

        device_name = raw_device_data[DEVICE_NAME_KEY]
        device_type = raw_device_data[DEVICE_TYPE_KEY]
        hub_id = raw_device_data[HUB_ID_KEY]
        device_id = raw_device_data[DEVICE_ID_KEY]

        self._attr_has_entity_name = True
        self._attr_name = "Remote"
        self._device_name = device_name
        self._device_type = device_type
        self._device_id = device_id
        self._hub_id = hub_id
        self._sw_version = raw_device_data.get(DEVICE_VERSION_KEY, "")

        # Generate entity ID
        self.entity_id = generate_entity_id(device_type, hub_id, device_id, "remote")

        # Remote control attributes
        self._attr_is_on = True  # Remote is always "on" as it's a control device
        self._attr_supported_features = (
            RemoteEntityFeature.LEARN_COMMAND | RemoteEntityFeature.DELETE_COMMAND
        )

        self._store = None
        self._learned_commands = {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub_id, self._device_id)},
            name=self._device_name,
            manufacturer="LifeSmart",
            model=self._device_type,
            sw_version=self._sw_version,
            via_device=(DOMAIN, self._hub_id),
        )

    @property
    def unique_id(self):
        """A unique identifier for this entity."""
        return self.entity_id

    async def async_turn_on(self, **kwargs):
        """Turn the remote on."""
        # Remote control is always "on" - this is a no-op
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the remote off."""
        # Remote control is always "on" - this is a no-op
        self._attr_is_on = True
        self.async_write_ha_state()

    @property
    def is_on(self):
        """Return true if the remote is on."""
        return self._attr_is_on

    async def async_send_command(self, command, **kwargs):
        """Send a command to the remote."""
        device = kwargs.get(ATTR_DEVICE)
        command_type = kwargs.get(ATTR_COMMAND_TYPE, "ir")
        num_repeats = kwargs.get(ATTR_NUM_REPEATS, 1)
        delay = kwargs.get(ATTR_DELAY_SECS, 0)

        _LOGGER.debug(
            "Sending command: %s, device: %s, type: %s, repeats: %s",
            command,
            device,
            command_type,
            num_repeats,
        )

        try:
            # If command is a list, send each command
            if isinstance(command, list):
                for cmd in command:
                    await self._send_single_command(cmd, device)
                    if delay > 0:
                        await asyncio.sleep(delay)
            else:
                await self._send_single_command(command, device)

        except Exception as e:
            _LOGGER.error("Error sending command: %s", e)
            raise

    async def _send_single_command(self, command, device=None):
        """Send a single IR command."""
        await self._async_load_commands()

        command_name = str(command)
        ir_code = self._get_learned_command(command_name, device)
        if ir_code is not None:
            await self._client.send_ir_code_async(
                self._hub_id, self._device_id, ir_code
            )
        else:
            # Preserve the old behavior: unknown commands are treated as raw IR data.
            target_device = device or self._device_id
            processed_code = command_name
            await self._client.send_ir_code_async(
                self._hub_id, target_device, processed_code
            )

    def _process_ir_code(self, code):
        """Process IR code, handling Base64 format if detected."""
        if not isinstance(code, str):
            return str(code)

        # Check if the code is Base64 encoded
        try:
            # Try to decode as Base64
            decoded_bytes = base64.b64decode(code, validate=True)
            # If successful, decode to string and return
            decoded_str = decoded_bytes.decode("utf-8", errors="ignore")
            _LOGGER.debug("Decoded Base64 IR code: %s -> %s", code, decoded_str)
            return decoded_str
        except (binascii.Error, ValueError):
            # Not valid Base64, treat as plain text
            _LOGGER.debug("IR code is not Base64 encoded: %s", code)
            return code

    async def async_learn_command(self, **kwargs):
        """Save a locally learned IR command."""
        command = _ensure_command_list(kwargs.get(ATTR_COMMAND))
        command_type = kwargs.get(ATTR_COMMAND_TYPE, "ir")
        device = kwargs.get(ATTR_DEVICE)

        if not command:
            _LOGGER.error("No command specified for learning")
            return

        ir_code, command_names = _extract_learned_ir_code(command, command_type)
        if not ir_code:
            raise ValueError(
                "Learning SPOT IR commands locally requires the IR payload in "
                "command_type, or command: [name, ir_code]."
            )

        _LOGGER.info(
            "Saving learned SPOT IR command: %s, device: %s", command_names, device
        )

        await self._async_load_commands()
        device_key = _command_device_key(device)
        self._learned_commands.setdefault(device_key, {})
        for command_name in command_names:
            self._learned_commands[device_key][command_name] = ir_code
        await self._async_save_commands()
        self.async_write_ha_state()

    async def async_delete_command(self, command, **kwargs):
        """Delete locally saved SPOT IR commands."""
        await self._async_load_commands()
        device = kwargs.get(ATTR_DEVICE)
        device_key = _command_device_key(device)
        deleted = False

        for command_name in _ensure_command_list(command):
            if self._learned_commands.get(device_key, {}).pop(command_name, None):
                deleted = True

        if not self._learned_commands.get(device_key):
            self._learned_commands.pop(device_key, None)

        if deleted:
            await self._async_save_commands()
            self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Load learned commands when added to hass."""
        self._store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)
        await self._async_load_commands()
        _LOGGER.debug("SPOT Remote added to HASS")

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        attrs = {
            "learned_commands": self._learned_command_names(),
            "device_type": self._device_type,
            "hub_id": self._hub_id,
            "device_id": self._device_id,
        }
        return attrs

    async def _async_load_commands(self):
        """Load learned IR commands from Home Assistant storage."""
        if self._learned_commands:
            return
        if self._store is None:
            if not self.hass:
                return
            self._store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)

        stored = await self._store.async_load()
        entity_commands = (
            stored.get("entities", {}).get(self.unique_id, {})
            if isinstance(stored, dict)
            else {}
        )
        self._learned_commands = _normalize_stored_commands(entity_commands)

    async def _async_save_commands(self):
        """Save learned IR commands to Home Assistant storage."""
        if self._store is None:
            self._store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)

        stored = await self._store.async_load()
        if not isinstance(stored, dict):
            stored = {}
        entities = stored.setdefault("entities", {})
        entities[self.unique_id] = self._learned_commands
        await self._store.async_save(stored)

    def _get_learned_command(self, command, device=None):
        """Return a locally saved IR code for the command."""
        device_key = _command_device_key(device)
        if command in self._learned_commands.get(device_key, {}):
            return self._learned_commands[device_key][command]
        return self._learned_commands.get(DEFAULT_COMMAND_DEVICE, {}).get(command)

    def _learned_command_names(self):
        """Return a stable list of learned command names for attributes."""
        names = []
        for device_key, commands in sorted(self._learned_commands.items()):
            for command in sorted(commands):
                if device_key == DEFAULT_COMMAND_DEVICE:
                    names.append(command)
                else:
                    names.append(f"{device_key}:{command}")
        return names


def _ensure_command_list(command) -> list[str]:
    """Return service command data as a list of strings."""
    if command is None:
        return []
    if isinstance(command, list):
        return [str(item) for item in command]
    return [str(command)]


def _command_device_key(device) -> str:
    """Return the local namespace for learned commands."""
    return str(device) if device else DEFAULT_COMMAND_DEVICE


def _extract_learned_ir_code(
    commands: list[str], command_type: str | None
) -> tuple[str | None, list[str]]:
    """Extract local IR payload and command names from learn service data."""
    if len(commands) == 2 and command_type in (None, DEFAULT_COMMAND_TYPE):
        return commands[1], [commands[0]]
    if command_type and command_type != DEFAULT_COMMAND_TYPE:
        return command_type, commands
    return None, commands


def _normalize_stored_commands(data: Any) -> dict[str, dict[str, str]]:
    """Normalize stored commands from previous local schemas."""
    if not isinstance(data, dict):
        return {}

    normalized = {}
    for device_key, commands in data.items():
        if isinstance(commands, dict):
            normalized[str(device_key)] = {
                str(command): str(ir_code)
                for command, ir_code in commands.items()
                if ir_code is not None
            }
        elif commands is not None:
            normalized.setdefault(DEFAULT_COMMAND_DEVICE, {})[str(device_key)] = str(
                commands
            )
    return normalized
