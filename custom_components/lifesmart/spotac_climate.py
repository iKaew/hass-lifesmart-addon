"""Support for LifeSmart SPOT AC remote control as climate entities."""

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from . import LifeSmartDevice, generate_entity_id
from .const import (
    CONF_AC_CONFIG,
    DEVICE_DATA_KEY,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DEVICE_VERSION_KEY,
    DOMAIN,
    HUB_ID_KEY,
    IR_CATEGORY_AC,
    SPOT_TYPES,
)

_LOGGER = logging.getLogger(__name__)

# AC mode mapping
AC_MODE_MAP = {
    "0": HVACMode.AUTO,
    "1": HVACMode.COOL,
    "2": HVACMode.DRY,
    "3": HVACMode.FAN_ONLY,
    "4": HVACMode.HEAT,
}

HVAC_MODE_TO_AC_MODE = {v: k for k, v in AC_MODE_MAP.items()}

# AC fan speeds
AC_FAN_MODES = {
    "0": "Auto",
    "1": "Speed 1",
    "2": "Speed 2",
    "3": "Speed 3",
}

FAN_MODE_TO_AC_SPEED = {v: k for k, v in AC_FAN_MODES.items()}

# AC swing modes
AC_SWING_MODES = {
    "0": "Auto",
    "1": "Direction 1",
    "2": "Direction 2",
    "3": "Direction 3",
    "4": "Direction 4",
}

SWING_MODE_TO_AC_SWING = {v: k for k, v in AC_SWING_MODES.items()}


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Setup SPOT AC climate entities."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    exclude_devices = hass.data[DOMAIN][config_entry.entry_id]["exclude_devices"]
    exclude_hubs = hass.data[DOMAIN][config_entry.entry_id]["exclude_hubs"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]

    ac_config = config_entry.options.get(
        CONF_AC_CONFIG,
        config_entry.data.get(CONF_AC_CONFIG, {}),
    )

    climate_devices = []

    for device in devices:
        if (
            device[DEVICE_ID_KEY] in exclude_devices
            or device[HUB_ID_KEY] in exclude_hubs
        ):
            continue

        device_type = device[DEVICE_TYPE_KEY]
        if device_type not in SPOT_TYPES:
            continue

        hub_id = device[HUB_ID_KEY]
        device_id = device[DEVICE_ID_KEY]

        # Check if AC is configured for this device
        device_key = f"{hub_id}_{device_id}"
        if device_key in ac_config:
            ac_info = ac_config[device_key]
            if ac_info.get("category") != IR_CATEGORY_AC:
                _LOGGER.warning(
                    "Skipping SPOT climate setup for %s because remote category is %s",
                    device_key,
                    ac_info.get("category"),
                )
                continue
            ha_device = LifeSmartDevice(device, client)
            climate_devices.append(
                LifeSmartSPOTACClimate(ha_device, device, client, ac_info)
            )

    async_add_entities(climate_devices)


class LifeSmartSPOTACClimate(ClimateEntity, RestoreEntity):
    """Representation of a LifeSmart SPOT AC remote control as climate entity."""

    def __init__(self, ha_device, raw_device_data, client, ac_info):
        """Initialize the AC climate entity."""
        self._device = ha_device
        self._raw_device_data = raw_device_data
        self._client = client
        self._ac_info = ac_info  # {"category": IR_CATEGORY_AC, "brand": "aux", "idx": "33.irxs"}

        device_name = raw_device_data[DEVICE_NAME_KEY]
        device_type = raw_device_data[DEVICE_TYPE_KEY]
        hub_id = raw_device_data[HUB_ID_KEY]
        device_id = raw_device_data[DEVICE_ID_KEY]

        self._attr_has_entity_name = True
        self._attr_name = f"AC {ac_info.get('brand', 'Unknown')}"
        self._device_name = device_name
        self._device_type = device_type
        self._device_id = device_id
        self._hub_id = hub_id
        self._sw_version = raw_device_data.get(DEVICE_VERSION_KEY, "")

        # Generate entity ID
        self.entity_id = generate_entity_id(
            device_type, hub_id, device_id, "climate_ac"
        )

        # Climate entity attributes
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_precision = PRECISION_WHOLE
        self._attr_target_temperature_step = 1
        self._attr_min_temp = 16
        self._attr_max_temp = 30

        # Default state
        self._attr_target_temperature = 25
        self._attr_hvac_mode = HVACMode.COOL
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.AUTO,
            HVACMode.COOL,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
            HVACMode.HEAT,
        ]
        self._attr_fan_mode = "Auto"
        self._attr_fan_modes = list(AC_FAN_MODES.values())
        self._attr_swing_mode = "Auto"
        self._attr_swing_modes = list(AC_SWING_MODES.values())

        # Supported features
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

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
        return f"{self.entity_id}_ac_{self._ac_info.get('brand', 'unknown')}"

    async def async_added_to_hass(self) -> None:
        """Restore the last known HA state after reload."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        if last_state.state in self._attr_hvac_modes:
            self._attr_hvac_mode = last_state.state

        target_temp = last_state.attributes.get("temperature")
        if target_temp is not None:
            self._attr_target_temperature = int(target_temp)

        fan_mode = last_state.attributes.get("fan_mode")
        if fan_mode in self._attr_fan_modes:
            self._attr_fan_mode = fan_mode

        swing_mode = last_state.attributes.get("swing_mode")
        if swing_mode in self._attr_swing_modes:
            self._attr_swing_mode = swing_mode

    async def async_turn_on(self, **kwargs):
        """Turn on the AC."""
        self._attr_hvac_mode = HVACMode.COOL
        await self._send_ac_command(
            key="power",
            power=0,
            mode=1,  # Cool
            temp=int(self._attr_target_temperature),
            wind=0,
            swing=0,
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn off the AC."""
        await self._send_ac_command(
            key="power",
            power=0,
            mode=0,
            temp=int(self._attr_target_temperature),
            wind=0,
            swing=0,
        )
        self._attr_hvac_mode = HVACMode.OFF
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        else:
            ac_mode = HVAC_MODE_TO_AC_MODE.get(hvac_mode, "1")
            await self._send_ac_command(
                key="mode",
                power=0,
                mode=int(ac_mode),
                temp=int(self._attr_target_temperature),
                wind=int(FAN_MODE_TO_AC_SPEED.get(self._attr_fan_mode, "0")),
                swing=int(SWING_MODE_TO_AC_SWING.get(self._attr_swing_mode, "0")),
            )
            self._attr_hvac_mode = hvac_mode
            self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is not None:
            self._attr_target_temperature = int(temperature)
            await self._send_ac_command(
                key="temp",
                power=1 if self._attr_hvac_mode == HVACMode.OFF else 0,
                mode=int(HVAC_MODE_TO_AC_MODE.get(self._attr_hvac_mode, "1")),
                temp=int(temperature),
                wind=int(FAN_MODE_TO_AC_SPEED.get(self._attr_fan_mode, "0")),
                swing=int(SWING_MODE_TO_AC_SWING.get(self._attr_swing_mode, "0")),
            )
            self.async_write_ha_state()

    async def async_set_target_temperature(self, **kwargs):
        """Backward-compatible wrapper for older callers."""
        await self.async_set_temperature(**kwargs)

    async def async_set_fan_mode(self, fan_mode: str):
        """Set fan mode."""
        self._attr_fan_mode = fan_mode
        await self._send_ac_command(
            key="wind",
            power=1 if self._attr_hvac_mode == HVACMode.OFF else 0,
            mode=int(HVAC_MODE_TO_AC_MODE.get(self._attr_hvac_mode, "1")),
            temp=int(self._attr_target_temperature),
            wind=int(FAN_MODE_TO_AC_SPEED.get(fan_mode, "0")),
            swing=int(SWING_MODE_TO_AC_SWING.get(self._attr_swing_mode, "0")),
        )
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str):
        """Set swing mode."""
        self._attr_swing_mode = swing_mode
        await self._send_ac_command(
            key="swing",
            power=1 if self._attr_hvac_mode == HVACMode.OFF else 0,
            mode=int(HVAC_MODE_TO_AC_MODE.get(self._attr_hvac_mode, "1")),
            temp=int(self._attr_target_temperature),
            wind=int(FAN_MODE_TO_AC_SPEED.get(self._attr_fan_mode, "0")),
            swing=int(SWING_MODE_TO_AC_SWING.get(swing_mode, "0")),
        )
        self.async_write_ha_state()

    async def _send_ac_command(self, key, power, mode, temp, wind, swing):
        """Send AC command via GetACCodes + SendCodes."""
        try:
            category = self._ac_info.get("category", IR_CATEGORY_AC)
            brand = self._ac_info.get("brand")
            idx = self._ac_info.get("idx")

            if not all([category, brand, idx]):
                _LOGGER.error("AC info incomplete: %s", self._ac_info)
                return
            if category != IR_CATEGORY_AC:
                _LOGGER.error("Invalid remote category for SPOT climate: %s", category)
                return

            ac_codes = await self._client.get_ac_codes_async(
                category=category,
                brand=brand,
                idx=idx,
                key=key,
                power=power,
                mode=mode,
                temp=temp,
                wind=wind,
                swing=swing,
            )

            ir_code = None
            if isinstance(ac_codes, dict):
                if "data" in ac_codes:
                    ir_code = ac_codes.get("data")
                elif "codes" in ac_codes and isinstance(ac_codes["codes"], list):
                    for code_entry in ac_codes["codes"]:
                        if isinstance(code_entry, dict) and code_entry.get("data"):
                            ir_code = code_entry.get("data")
                            break
                elif key in ac_codes and isinstance(ac_codes[key], dict):
                    ir_code = ac_codes[key].get("data")
                elif key.upper() in ac_codes and isinstance(
                    ac_codes[key.upper()], dict
                ):
                    ir_code = ac_codes[key.upper()].get("data")
            elif isinstance(ac_codes, list) and ac_codes:
                first = ac_codes[0]
                if isinstance(first, dict):
                    ir_code = first.get("data")
                else:
                    ir_code = first
            elif isinstance(ac_codes, str):
                ir_code = ac_codes

            if not ir_code:
                _LOGGER.error("No IR code returned for AC command: %s", ac_codes)
                return

            response = await self._client.send_ir_code_async(
                self._hub_id,
                self._device_id,
                ir_code,
            )
            _LOGGER.debug("AC command code response: %s", response)
        except Exception as e:
            _LOGGER.error("Error sending AC command: %s", e)
