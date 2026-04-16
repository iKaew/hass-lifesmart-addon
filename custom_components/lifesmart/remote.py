"""Support for LifeSmart SPOT IR remote controls."""

import asyncio
import base64
import binascii
import logging

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

from . import LifeSmartDevice, generate_entity_id
from .const import (
    DEVICE_DATA_KEY,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DEVICE_VERSION_KEY,
    DOMAIN,
    HUB_ID_KEY,
    SPOT_TYPES,
)

_LOGGER = logging.getLogger(__name__)


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
        self._attr_supported_features = RemoteEntityFeature.LEARN_COMMAND

        # Store learned IR codes
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
                    await self._send_single_command(cmd, device, delay)
                    if delay > 0:
                        await asyncio.sleep(delay)
            else:
                await self._send_single_command(command, device, delay)

        except Exception as e:
            _LOGGER.error("Error sending command: %s", e)
            raise

    async def _send_single_command(self, command, device=None, delay=0):
        """Send a single IR command."""
        # If device is specified, use it; otherwise use the SPOT device itself
        target_device = device or self._device_id

        # Check if this is a learned command
        if (command,) in self._learned_commands:
            ir_code = self._learned_commands[(command,)]
            await self._client.send_ir_code_async(self._hub_id, target_device, ir_code)
        else:
            # Process the command - could be direct IR code or Base64 encoded
            processed_code = command  # self._process_ir_code(command)
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
        """Learn a command from the remote."""
        command = kwargs.get(ATTR_COMMAND)
        command_type = kwargs.get(ATTR_COMMAND_TYPE, "ir")
        device = kwargs.get(ATTR_DEVICE)

        if not command:
            _LOGGER.error("No command specified for learning")
            return

        _LOGGER.info(
            "Learning command: %s, type: %s, device: %s", command, command_type, device
        )

        try:
            # Get IR remote list to see available remotes
            remote_list = await self._client.get_ir_remote_list_async(self._hub_id)

            if remote_list:
                # For now, just log the available remotes
                # In a full implementation, this would guide the learning process
                _LOGGER.debug("Available IR remotes: %s", remote_list)

                # Store a placeholder - actual learning would require user interaction
                self._learned_commands[tuple(command)] = f"learned_{command}"
                _LOGGER.info("Command '%s' marked as learned (placeholder)", command)
            else:
                _LOGGER.warning("No IR remotes available for learning")

        except Exception as e:
            _LOGGER.error("Error learning command: %s", e)
            raise

    async def async_added_to_hass(self):
        """Load learned commands when added to hass."""
        # Load any previously learned commands
        # This would typically load from stored configuration
        _LOGGER.debug("SPOT Remote added to HASS")

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        attrs = {
            "learned_commands": list(self._learned_commands.keys()),
            "device_type": self._device_type,
            "hub_id": self._hub_id,
            "device_id": self._device_id,
        }
        return attrs
