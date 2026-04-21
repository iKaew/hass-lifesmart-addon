"""Support for LifeSmart NATURE thermostat climate entities."""

import asyncio

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
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
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    MANUFACTURER,
    NATURE_CLIMATE_KEY,
    is_nature_thermostat,
)


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Setup NATURE thermostat climate entities."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    exclude_devices = hass.data[DOMAIN][config_entry.entry_id]["exclude_devices"]
    exclude_hubs = hass.data[DOMAIN][config_entry.entry_id]["exclude_hubs"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]

    climate_devices = []
    for device in devices:
        if (
            device[DEVICE_ID_KEY] in exclude_devices
            or device[HUB_ID_KEY] in exclude_hubs
            or not is_nature_thermostat(device)
        ):
            continue

        climate_devices.append(
            LifeSmartNatureClimate(LifeSmartDevice(device, client), device, client)
        )

    async_add_entities(climate_devices)


class LifeSmartNatureClimate(ClimateEntity):
    """LifeSmart NATURE thermostat climate entity."""

    def __init__(self, ha_device, raw_device_data, client):
        """Initialize the NATURE thermostat."""
        self._device = ha_device
        self._raw_device_data = raw_device_data
        self._client = client
        self._name = raw_device_data[DEVICE_NAME_KEY]
        self._device_type = raw_device_data[DEVICE_TYPE_KEY]
        self._hub_id = raw_device_data[HUB_ID_KEY]
        self._device_id = raw_device_data[DEVICE_ID_KEY]
        self._sw_version = raw_device_data.get(DEVICE_VERSION_KEY, "")
        self.entity_id = generate_entity_id(
            self._device_type, self._hub_id, self._device_id, NATURE_CLIMATE_KEY
        )

        cdata = raw_device_data[DEVICE_DATA_KEY]
        self._mode = (
            _nature_mode_from_value(cdata.get("P7", {}).get("val"))
            if cdata["P1"]["type"] % 2 == 1
            else HVACMode.OFF
        )
        self._target_temperature = _temperature_value(
            cdata.get("P8", {}).get("v"), cdata.get("P8", {}).get("val")
        )
        self._current_temperature = _temperature_value(
            cdata.get("P4", {}).get("v"), cdata.get("P4", {}).get("val")
        )
        self._fanspeed = cdata.get("P10", {}).get("val")
        self._attributes = {
            HUB_ID_KEY: self._hub_id,
            DEVICE_ID_KEY: self._device_id,
            "devtype": self._device_type,
            "cfg": cdata.get("P6", {}).get("val"),
            "gate_1": cdata.get("P2", {}).get("val"),
            "gate_2": cdata.get("P3", {}).get("val"),
        }

    @property
    def unique_id(self):
        """A unique identifier for this entity."""
        return self.entity_id

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub_id, self._device_id)},
            name=self._name,
            manufacturer=MANUFACTURER,
            model=self._device_type,
            sw_version=self._sw_version,
            via_device=(DOMAIN, self._hub_id),
        )

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return self._attributes

    @property
    def hvac_mode(self):
        """Return current HVAC mode."""
        return self._mode

    @property
    def hvac_modes(self):
        """Return supported HVAC modes."""
        return [
            HVACMode.OFF,
            HVACMode.AUTO,
            HVACMode.FAN_ONLY,
            HVACMode.COOL,
            HVACMode.HEAT,
        ]

    @property
    def current_temperature(self):
        """Return current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return target temperature."""
        return self._target_temperature

    @property
    def min_temp(self):
        """Return minimum target temperature."""
        return 5

    @property
    def max_temp(self):
        """Return maximum target temperature."""
        return 35

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def temperature_unit(self):
        """Return the unit of measurement used by the platform."""
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature_step(self):
        """Return the supported target temperature step."""
        return 0.5

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return _get_nature_fan_mode(self._fanspeed)

    @property
    def fan_modes(self):
        """Return supported fan modes."""
        return [FAN_LOW, FAN_MEDIUM, FAN_HIGH, "auto", "off"]

    @property
    def supported_features(self):
        """Return the supported features."""
        return ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE

    async def async_set_temperature(self, **kwargs):
        """Set target temperature."""
        if "temperature" not in kwargs:
            return
        target_temperature = kwargs["temperature"]
        result = await self._device.async_lifesmart_epset(
            "0x89", int(target_temperature * 10), "P8"
        )
        if result == 0:
            self._target_temperature = target_temperature
            self.async_schedule_update_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        result = await self._device.async_lifesmart_epset(
            "0xCF", _get_nature_fan_speed(fan_mode), "P9"
        )
        if result == 0:
            self._fanspeed = _get_nature_fan_speed(fan_mode)
            self.async_schedule_update_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            result = await self._device.async_lifesmart_epset("0x80", 0, "P1")
            if result == 0:
                self._mode = HVACMode.OFF
                self.async_schedule_update_ha_state()
            return

        if self._mode == HVACMode.OFF:
            if await self._device.async_lifesmart_epset("0x81", 1, "P1") == 0:
                await asyncio.sleep(1)
            else:
                return

        result = await self._device.async_lifesmart_epset(
            "0xCF", _nature_mode_to_value(hvac_mode), "P7"
        )
        if result == 0:
            self._mode = hvac_mode
            self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{self.entity_id}",
                self._update_state,
            )
        )

    async def _update_state(self, data) -> None:
        """Update state from LifeSmart websocket data."""
        idx = data.get("idx")
        value = data.get("val")

        if idx == "P1":
            self._mode = HVACMode.OFF if data.get("type", 0) % 2 == 0 else self._mode
            if self._mode == HVACMode.OFF and data.get("type", 0) % 2 == 1:
                self._mode = HVACMode.AUTO
        elif idx == "P4":
            self._current_temperature = _temperature_value(data.get("v"), value)
        elif idx == "P7":
            if self._mode != HVACMode.OFF:
                self._mode = _nature_mode_from_value(value)
        elif idx == "P8":
            self._target_temperature = _temperature_value(data.get("v"), value)
        elif idx == "P9":
            self._fanspeed = value
        elif idx == "P10":
            self._fanspeed = value

        self.async_schedule_update_ha_state()


def _get_fan_mode(fanspeed):
    """Convert LifeSmart fan speed to Home Assistant fan mode."""
    if fanspeed is None:
        return None
    if fanspeed < 30:
        return FAN_LOW
    if fanspeed < 65:
        return FAN_MEDIUM
    return FAN_HIGH


def _get_nature_fan_mode(fanspeed):
    """Convert NATURE fan speed to Home Assistant fan mode."""
    if fanspeed is None:
        return None
    if fanspeed == 0:
        return "off"
    if fanspeed == 101:
        return "auto"
    return _get_fan_mode(fanspeed)


def _get_nature_fan_speed(fan_mode):
    """Convert Home Assistant fan mode to NATURE fan speed."""
    return {
        FAN_LOW: 15,
        FAN_MEDIUM: 45,
        FAN_HIGH: 75,
        "auto": 101,
        "off": 0,
    }[fan_mode]


def _nature_mode_from_value(value):
    """Map NATURE MODE values to Home Assistant HVAC modes."""
    return {
        1: HVACMode.AUTO,
        2: HVACMode.FAN_ONLY,
        3: HVACMode.COOL,
        4: HVACMode.HEAT,
        7: HVACMode.HEAT,
        8: HVACMode.HEAT,
    }.get(value, HVACMode.AUTO)


def _nature_mode_to_value(hvac_mode):
    """Map Home Assistant HVAC modes to NATURE MODE values."""
    return {
        HVACMode.AUTO: 1,
        HVACMode.FAN_ONLY: 2,
        HVACMode.COOL: 3,
        HVACMode.HEAT: 4,
    }[hvac_mode]


def _temperature_value(display_value, raw_value):
    """Return LifeSmart display temperature, falling back to raw tenths."""
    if display_value is not None:
        return display_value
    if raw_value is not None:
        return raw_value / 10
    return None
