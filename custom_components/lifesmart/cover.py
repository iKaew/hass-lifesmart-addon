"""Support for LifeSmart covers."""

import logging

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)

from . import LifeSmartDevice
from .const import (
    COVER_TYPES,
    DEVICE_DATA_KEY,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DOMAIN,
    HUB_ID_KEY,
)

_LOGGER = logging.getLogger(__name__)

# Device type specific configurations for curtain control
CURTAIN_DEVICE_CONFIG = {
    # Position-based devices (support set_position)
    "SL_DOOYA": {
        "status_idx": "P1",
        "control_idx": "P2",
        "type": "position",
        "supports_position": True,
    },
    "SL_DOOYA_V2": {
        "status_idx": "P1",
        "control_idx": "P2",
        "type": "position",
        "supports_position": True,
    },
    "SL_DOOYA_V3": {
        "status_idx": "P1",
        "control_idx": "P2",
        "type": "position",
        "supports_position": True,
    },
    "SL_DOOYA_V4": {
        "status_idx": "P1",
        "control_idx": "P2",
        "type": "position",
        "supports_position": True,
    },
    # Function-based devices (Open/Stop/Close only)
    "SL_SW_WIN": {
        "open_idx": "OP",
        "stop_idx": "ST",
        "close_idx": "CL",
        "type": "function",
        "supports_position": False,
    },
    "SL_CN_IF": {
        "open_idx": "P1",
        "stop_idx": "P2",
        "close_idx": "P3",
        "type": "function",
        "supports_position": False,
    },
    "SL_CN_FE": {
        "open_idx": "P1",
        "stop_idx": "P2",
        "close_idx": "P3",
        "type": "function",
        "supports_position": False,
    },
    "SL_P_V2": {
        "open_idx": "P2",
        "stop_idx": "P4",
        "close_idx": "P3",
        "type": "function",
        "supports_position": False,
    },
    "SL_ETDOOR": {
        "status_idx": "P2",
        "control_idx": "P3",
        "type": "position",
        "supports_position": True,
        "device_class": CoverDeviceClass.GARAGE,
    },
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup cover entities."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    exclude_devices = hass.data[DOMAIN][config_entry.entry_id]["exclude_devices"]
    exclude_hubs = hass.data[DOMAIN][config_entry.entry_id]["exclude_hubs"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]
    cover_devices = []

    for device in devices:
        if (
            device[DEVICE_ID_KEY] in exclude_devices
            or device[HUB_ID_KEY] in exclude_hubs
        ):
            continue

        device_type = device[DEVICE_TYPE_KEY]
        if device_type not in COVER_TYPES:
            continue

        # Get device configuration
        device_config = CURTAIN_DEVICE_CONFIG.get(device_type)
        if not device_config:
            _LOGGER.warning(f"Configuration missing for device type: {device_type}")
            continue

        # Position-based devices
        if device_config.get("type") == "position":
            status_idx = device_config.get("status_idx")
            if status_idx in device.get(DEVICE_DATA_KEY, {}):
                ha_device = LifeSmartDevice(device, client)
                cover_devices.append(
                    LifeSmartCover(
                        ha_device,
                        device,
                        status_idx,
                        device[DEVICE_DATA_KEY][status_idx],
                        device_config,
                    )
                )

        # Function-based devices
        elif device_config.get("type") == "function":
            # Use the open index as the main identifier
            open_idx = device_config.get("open_idx")
            if open_idx in device.get(DEVICE_DATA_KEY, {}):
                ha_device = LifeSmartDevice(device, client)
                cover_devices.append(
                    LifeSmartCover(
                        ha_device,
                        device,
                        open_idx,
                        device[DEVICE_DATA_KEY][open_idx],
                        device_config,
                    )
                )

    async_add_entities(cover_devices)


class LifeSmartCover(CoverEntity):
    """LifeSmart cover devices."""

    def __init__(self, ha_device, raw_device_data, idx, sub_device_data, device_config):
        """Init LifeSmart cover device."""
        self._device = ha_device
        self._raw_device_data = raw_device_data
        self._idx = idx
        self._sub_device_data = sub_device_data
        self._device_config = device_config

        device_name = raw_device_data[DEVICE_NAME_KEY]
        device_type = raw_device_data[DEVICE_TYPE_KEY]
        hub_id = raw_device_data[HUB_ID_KEY]
        device_id = raw_device_data[DEVICE_ID_KEY]

        # Generate entity ID
        self.entity_id = (
            "cover." + (device_type + "_" + hub_id + "_" + device_id).lower()
        )

        # Initialize position based on device type
        if device_config.get("type") == "position":
            self._pos = sub_device_data.get("val", 0) & 0x7F
            self._moving = sub_device_data.get("type", 0) % 2 == 1
            self._opening = self._moving and sub_device_data.get("val", 0) & 0x80 == 0x80
        else:
            self._pos = None
            self._moving = None
            self._opening = None

        self._attr_name = device_name
        self._attr_device_class = device_config.get("device_class", CoverDeviceClass.CURTAIN)
        self._attr_unique_id = self.entity_id

    @property
    def should_poll(self):
        """Check with the entity for an updated state."""
        return False

    @property
    def supported_features(self):
        """Return the supported features."""
        features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        )

        if self._device_config.get("supports_position"):
            features |= CoverEntityFeature.SET_POSITION

        return features

    @property
    def current_cover_position(self):
        """Return the current position of the cover."""
        if self._device_config.get("supports_position"):
            return self._pos
        return None

    @property
    def is_closed(self):
        """Return if the cover is closed."""
        if self._device_config.get("supports_position"):
            return self._pos <= 0
        # For function-based devices, we don't know the position, so return None
        return None

    @property
    def is_closing(self):
        """Return if the cover is closing."""
        if self._device_config.get("type") == "position" and self._pos is not None:
            return self._moving and not self._opening
        return None

    @property
    def is_opening(self):
        """Return if the cover is opening."""
        if self._device_config.get("type") == "position" and self._pos is not None:
            return self._moving and self._opening
        return None

    async def async_close_cover(self, **kwargs):
        """Close the cover."""
        device_config = self._device_config
        if device_config.get("type") == "position":
            # Position-based devices: set to 0 (closed)
            await self._device.async_lifesmart_epset(
                "0xCF", 0, device_config.get("control_idx")
            )
        else:
            # Function-based devices: use close command
            close_idx = device_config.get("close_idx")
            await self._device.async_lifesmart_epset("0x81", 1, close_idx)

    async def async_open_cover(self, **kwargs):
        """Open the cover."""
        device_config = self._device_config
        if device_config.get("type") == "position":
            # Position-based devices: set to 100 (fully open)
            await self._device.async_lifesmart_epset(
                "0xCF", 100, device_config.get("control_idx")
            )
        else:
            # Function-based devices: use open command
            open_idx = device_config.get("open_idx")
            await self._device.async_lifesmart_epset("0x81", 1, open_idx)

    async def async_stop_cover(self, **kwargs):
        """Stop the cover."""
        device_config = self._device_config
        if device_config.get("type") == "position":
            # Position-based devices: use 0xCE with 0x80 to stop
            await self._device.async_lifesmart_epset(
                "0xCE", 0x80, device_config.get("control_idx")
            )
        else:
            # Function-based devices: use stop command
            stop_idx = device_config.get("stop_idx")
            await self._device.async_lifesmart_epset("0x81", 1, stop_idx)

    async def async_set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        if not self._device_config.get("supports_position"):
            _LOGGER.warning(
                "Device %s does not support position control",
                self._raw_device_data.get(DEVICE_TYPE_KEY),
            )
            return

        position = kwargs.get(ATTR_POSITION)
        await self._device.async_lifesmart_epset(
            "0xCE", position, self._device_config.get("control_idx")
        )
