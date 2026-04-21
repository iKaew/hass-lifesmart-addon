"""Support for the LifeSmart climate devices."""

import asyncio
import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import PRECISION_WHOLE, UnitOfTemperature
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from . import LifeSmartDevice, generate_entity_id
from .const import (
    AIR_CONDITIONER_TYPES,
    CLIMATE_TYPES,
    DEVICE_DATA_KEY,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DEVICE_VERSION_KEY,
    DOMAIN,
    HUB_ID_KEY,
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    MANUFACTURER,
    THERMOSTAT_TYPES,
)
from .nature_climate import async_setup_entry as async_setup_nature_entry
from .spotac_climate import async_setup_entry as async_setup_spotac_entry

_LOGGER = logging.getLogger(__name__)
DEVICE_TYPE = "climate"

LIFESMART_STATE_LIST = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.FAN_ONLY,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
]

LIFESMART_STATE_LIST2 = [
    HVACMode.OFF,
    HVACMode.HEAT,
]

FAN_MODES = [FAN_LOW, FAN_MEDIUM, FAN_HIGH]
GET_FAN_SPEED = {FAN_LOW: 15, FAN_MEDIUM: 45, FAN_HIGH: 75}

AIR_TYPES = AIR_CONDITIONER_TYPES

THER_TYPES = THERMOSTAT_TYPES


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up LifeSmart Climate entities from config entry."""
    await async_setup_spotac_entry(hass, config_entry, async_add_entities)
    await async_setup_nature_entry(hass, config_entry, async_add_entities)

    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    exclude_devices = hass.data[DOMAIN][config_entry.entry_id]["exclude_devices"]
    exclude_hubs = hass.data[DOMAIN][config_entry.entry_id]["exclude_hubs"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]

    climate_devices = []
    for device in devices:
        if (
            device[DEVICE_ID_KEY] in exclude_devices
            or device[HUB_ID_KEY] in exclude_hubs
        ):
            continue

        device_type = device[DEVICE_TYPE_KEY]
        if device_type not in CLIMATE_TYPES:
            continue

        if not _has_required_climate_data(device):
            _LOGGER.warning(
                "Skipping unsupported or incomplete climate device %s (%s)",
                device.get(DEVICE_NAME_KEY, device.get(DEVICE_ID_KEY)),
                device_type,
            )
            continue

        climate_devices.append(
            LifeSmartClimateDevice(LifeSmartDevice(device, client), device, client)
        )

    async_add_entities(climate_devices)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up LifeSmart Climate devices."""
    if discovery_info is None:
        return
    devices = []
    dev = discovery_info.get("dev")
    client = discovery_info.get("param")
    if client is None or dev is None:
        return
    if not _has_required_climate_data(dev):
        return
    devices.append(LifeSmartClimateDevice(LifeSmartDevice(dev, client), dev, client))
    async_add_entities(devices)


class LifeSmartClimateDevice(LifeSmartDevice, ClimateEntity):
    """LifeSmart climate devices,include air conditioner,heater."""

    def __init__(self, ha_device, raw_device_data, client):
        """Init LifeSmart climate device."""
        super().__init__(raw_device_data, client)
        self._device = ha_device
        self._raw_device_data = raw_device_data
        self._client = client
        self._name = raw_device_data[DEVICE_NAME_KEY]
        self._device_type = raw_device_data[DEVICE_TYPE_KEY]
        self._hub_id = raw_device_data[HUB_ID_KEY]
        self._device_id = raw_device_data[DEVICE_ID_KEY]
        self._sw_version = raw_device_data.get(DEVICE_VERSION_KEY, "")
        self.entity_id = generate_entity_id(
            self._device_type, self._hub_id, self._device_id
        )

        cdata = raw_device_data[DEVICE_DATA_KEY]
        self._fanspeed = None

        if self._device_type in AIR_TYPES:
            self._modes = LIFESMART_STATE_LIST
            self._mode = self._mode_from_air_data(cdata)
            self._last_mode = self._mode_from_mode_value(cdata["MODE"].get("val", 1))
            if self._last_mode == HVACMode.OFF:
                self._last_mode = HVACMode.AUTO
            self._current_temperature = cdata["T"].get("v")
            self._target_temperature = cdata["tT"].get("v")
            if self._target_temperature is None:
                self._target_temperature = cdata["tT"].get("val", 0) / 10
            self._min_temp = 10
            self._max_temp = 35
            self._fanspeed = cdata["F"].get("val", 0)
            self._attributes.update({"last_mode": self._last_mode})
        else:
            self._modes = LIFESMART_STATE_LIST2
            if cdata["P1"]["type"] % 2 == 0:
                self._mode = HVACMode.OFF
            else:
                self._mode = HVACMode.HEAT
            if cdata["P2"]["type"] % 2 == 0:
                self._attributes.setdefault("Heating", "false")
            else:
                self._attributes.setdefault("Heating", "true")
            self._current_temperature = cdata["P4"].get("v", cdata["P4"]["val"] / 10)
            self._target_temperature = cdata["P3"].get("v", cdata["P3"]["val"] / 10)
            self._min_temp = 5
            self._max_temp = 35

    @staticmethod
    def _mode_from_mode_value(value):
        """Map LifeSmart mode values to Home Assistant HVAC modes."""
        if value is None or value < 0 or value >= len(LIFESMART_STATE_LIST):
            return HVACMode.AUTO
        return LIFESMART_STATE_LIST[value]

    def _mode_from_air_data(self, cdata):
        """Return the active LifeSmart air-board mode from data."""
        if cdata["O"]["type"] % 2 == 0:
            return HVACMode.OFF
        return self._mode_from_mode_value(cdata["MODE"].get("val", 1))

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
    def hvac_mode(self):
        """Return current HVAC mode."""
        return self._mode

    @property
    def hvac_modes(self):
        """Return the list of available HVAC modes."""
        return self._modes

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
        return self._min_temp

    @property
    def max_temp(self):
        """Return maximum target temperature."""
        return self._max_temp

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
        """Return the supported step of target temperature."""
        return 1

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return _get_fan_mode(self._fanspeed)

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        if self._devtype in AIR_TYPES:
            return FAN_MODES
        return None

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if "temperature" not in kwargs:
            return
        target_temperature = kwargs["temperature"]
        new_temp = int(target_temperature * 10)
        _LOGGER.info("set_temperature: %s", str(new_temp))
        if self._devtype in AIR_TYPES:
            result = await self._device.async_lifesmart_epset("0x88", new_temp, "tT")
        else:
            result = await self._device.async_lifesmart_epset("0x88", new_temp, "P3")
        if result == 0:
            self._target_temperature = target_temperature
            self.async_schedule_update_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        result = await self._device.async_lifesmart_epset(
            "0xCE", GET_FAN_SPEED[fan_mode], "F"
        )
        if result == 0:
            self._fanspeed = GET_FAN_SPEED[fan_mode]
            self.async_schedule_update_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target operation mode."""
        if self._devtype in AIR_TYPES:
            if hvac_mode == HVACMode.OFF:
                result = await self._device.async_lifesmart_epset("0x80", 0, "O")
                if result == 0:
                    self._mode = HVACMode.OFF
                    self.async_schedule_update_ha_state()
                return
            if self._mode == HVACMode.OFF:
                if await self._device.async_lifesmart_epset("0x81", 1, "O") == 0:
                    await asyncio.sleep(2)
                else:
                    return
            result = await self._device.async_lifesmart_epset(
                "0xCE", LIFESMART_STATE_LIST.index(hvac_mode), "MODE"
            )
            if result == 0:
                self._mode = hvac_mode
                self._last_mode = hvac_mode
                self._attributes["last_mode"] = hvac_mode
                self.async_schedule_update_ha_state()
        elif hvac_mode == HVACMode.OFF:
            await self._device.async_lifesmart_epset("0x80", 0, "P1")
            await asyncio.sleep(1)
            await self._device.async_lifesmart_epset("0x80", 0, "P2")
            self._mode = HVACMode.OFF
            self.async_schedule_update_ha_state()
            return
        elif await self._device.async_lifesmart_epset("0x81", 1, "P1") == 0:
            await asyncio.sleep(2)
            self._mode = HVACMode.HEAT
            self.async_schedule_update_ha_state()
        else:
            return

    @property
    def supported_features(self):
        """Return the list of supported features."""
        if self._devtype in AIR_TYPES:
            return (
                ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
            )
        else:
            return ClimateEntityFeature.TARGET_TEMPERATURE

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
        display_value = data.get("v")
        data_type = data.get("type")

        if self._devtype in AIR_TYPES:
            if idx == "O":
                if data_type % 2 == 1:
                    self._mode = self._last_mode
                else:
                    self._mode = HVACMode.OFF
            elif idx == "MODE" and data_type == 0xCE:
                mode = self._mode_from_mode_value(value)
                self._last_mode = mode
                self._attributes["last_mode"] = mode
                if self._mode != HVACMode.OFF:
                    self._mode = mode
            elif idx == "F" and data_type == 0xCE:
                self._fanspeed = value
            elif idx == "tT" and data_type == 0x88:
                self._target_temperature = _temperature_value(display_value, value)
            elif idx == "T" and data_type in (0x08, 0x09):
                self._current_temperature = _temperature_value(display_value, value)
        else:
            if idx == "P1":
                self._mode = HVACMode.HEAT if data_type % 2 == 1 else HVACMode.OFF
            elif idx == "P2":
                self._attributes["Heating"] = "true" if data_type % 2 == 1 else "false"
            elif idx == "P3" and data_type == 0x88:
                self._target_temperature = _temperature_value(display_value, value)
            elif idx == "P4" and data_type in (0x08, 0x09):
                self._current_temperature = _temperature_value(display_value, value)

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


def _has_required_climate_data(device):
    """Return whether a LifeSmart climate device has the required IO data."""
    cdata = device.get(DEVICE_DATA_KEY, {})
    device_type = device.get(DEVICE_TYPE_KEY)
    if device_type in AIR_TYPES:
        return all(idx in cdata for idx in ("O", "MODE", "F", "tT", "T"))
    if device_type in THER_TYPES:
        return all(idx in cdata for idx in ("P1", "P2", "P3", "P4"))
    return False


def _temperature_value(display_value, raw_value):
    """Return LifeSmart display temperature, falling back to raw tenths."""
    if display_value is not None:
        return display_value
    if raw_value is not None:
        return raw_value / 10
    return None
