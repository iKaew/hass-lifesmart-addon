"""Support for lifesmart sensors."""

import logging
import struct

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    LIGHT_LUX,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfSoundPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

# DOMAIN = "sensor"
# ENTITY_ID_FORMAT = DOMAIN + ".{}"
from . import LifeSmartDevice, generate_entity_id
from .const import (
    AIR_PURIFIER_TYPES,
    CO2_SENSOR_TYPES,
    DEFED_SENSOR_TYPES,
    DEVICE_DATA_KEY,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DEVICE_VERSION_KEY,
    DIGITAL_DOORLOCK_BATTERY_EVENT_KEY,
    DIGITAL_DOORLOCK_OPERATION_EVENT_KEY,
    DLT_METER_TYPES,
    DOMAIN,
    ELECTRICITY_METER_TYPES,
    ENV_SENSOR_TYPES,
    GAS_SENSOR_TYPES,
    HUB_ID_KEY,
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    LOCK_TYPES,
    MANUFACTURER,
    MODBUS_CONTROLLER_TYPES,
    MOTION_SENSOR_TYPES,
    NATURE_TYPES,
    NOISE_SENSOR_TYPES,
    OT_SENSOR_TYPES,
    SMART_PLUG_TYPES,
    SMOKE_SENSOR_TYPES,
    TVOC_CO2_SENSOR_TYPES,
    WATER_LEAK_SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)

AIR_PURIFIER_MODES = {
    0: "auto",
    1: "fan_1",
    2: "fan_2",
    3: "fan_3",
    4: "max",
    5: "sleep",
}

MODBUS_SENSOR_KEYS = {
    "P1",
    "EE",
    "EP",
    "EPF",
    "EF",
    "EI",
    "EV",
    "T",
    "H",
    "PM",
    "COPPM",
    "CO2PPM",
    "CH2OPPM",
    "O2VOL",
    "NH3PPM",
    "H2SPPM",
    "TVOC",
    "PHM",
    "SMOKE",
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Setup Switch entities."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    exclude_devices = hass.data[DOMAIN][config_entry.entry_id]["exclude_devices"]
    exclude_hubs = hass.data[DOMAIN][config_entry.entry_id]["exclude_hubs"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]
    sensor_devices = []
    for device in devices:
        if (
            device[DEVICE_ID_KEY] in exclude_devices
            or device[HUB_ID_KEY] in exclude_hubs
        ):
            continue

        device_type = device[DEVICE_TYPE_KEY]
        supported_sensors = (
            OT_SENSOR_TYPES
            + GAS_SENSOR_TYPES
            + LOCK_TYPES
            + SMART_PLUG_TYPES
            + NATURE_TYPES
            + WATER_LEAK_SENSOR_TYPES
            + CO2_SENSOR_TYPES
            + DEFED_SENSOR_TYPES
            + ENV_SENSOR_TYPES
            + TVOC_CO2_SENSOR_TYPES
            + MOTION_SENSOR_TYPES
            + SMOKE_SENSOR_TYPES
            + NOISE_SENSOR_TYPES
            + ELECTRICITY_METER_TYPES
            + AIR_PURIFIER_TYPES
            + DLT_METER_TYPES
            + MODBUS_CONTROLLER_TYPES
        )

        if device_type not in supported_sensors:
            continue

        ha_device = LifeSmartDevice(
            device,
            client,
        )
        for sub_device_key in device[DEVICE_DATA_KEY]:
            sub_device_data = device[DEVICE_DATA_KEY][sub_device_key]
            if device_type in OT_SENSOR_TYPES and sub_device_key in [  # noqa: SIM114
                "Z",
                "V",
                "P3",
                "P4",
            ]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in GAS_SENSOR_TYPES and sub_device_key in ["P1", "P2"]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in LOCK_TYPES and sub_device_key in [  # noqa: SIM114
                DIGITAL_DOORLOCK_BATTERY_EVENT_KEY
            ]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif (
                device_type in LOCK_TYPES
                and sub_device_key == DIGITAL_DOORLOCK_OPERATION_EVENT_KEY
            ):
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in SMART_PLUG_TYPES and sub_device_key in ["P2", "P3"]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in NATURE_TYPES and sub_device_key == "P4":
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in WATER_LEAK_SENSOR_TYPES and sub_device_key == "V":
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in CO2_SENSOR_TYPES and sub_device_key in [
                "P1",
                "P2",
                "P3",
                "P4",
            ]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in ENV_SENSOR_TYPES and sub_device_key in [
                "T",
                "H",
                "Z",
                "V",
            ]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in TVOC_CO2_SENSOR_TYPES and sub_device_key in [
                "P1",
                "P2",
                "P3",
                "P4",
                "P5",
                "P6",
            ]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in DEFED_SENSOR_TYPES and sub_device_key in ["T", "V"]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in ELECTRICITY_METER_TYPES and sub_device_key == "EPA":
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in DLT_METER_TYPES and sub_device_key in ["EE", "EP"]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in MODBUS_CONTROLLER_TYPES and _is_modbus_sensor_key(
                sub_device_key
            ):
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in AIR_PURIFIER_TYPES and sub_device_key in [
                "RM",
                "T",
                "H",
                "PM",
                "FL",
                "UV",
            ]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in NOISE_SENSOR_TYPES and sub_device_key in [
                "P1",
                "P2",
                "P4",
            ]:
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type == "SL_SC_CM" and sub_device_key == "P3":
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in SMOKE_SENSOR_TYPES and sub_device_key == "P2":
                sensor_devices.append(
                    LifeSmartSensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
    async_add_entities(sensor_devices)


class LifeSmartSensor(SensorEntity):
    """Representation of a LifeSmartSensor."""

    # def __init__(self, dev, idx, val, param) -> None:
    def __init__(
        self, device, raw_device_data, sub_device_key, sub_device_data, client
    ) -> None:
        """Initialize the LifeSmartSensor."""

        super().__init__()

        device_name = raw_device_data[DEVICE_NAME_KEY]
        device_type = raw_device_data[DEVICE_TYPE_KEY]
        hub_id = raw_device_data[HUB_ID_KEY]
        device_id = raw_device_data[DEVICE_ID_KEY]

        if (
            DEVICE_NAME_KEY in sub_device_data
            and sub_device_data[DEVICE_NAME_KEY] != "none"
        ):
            device_name = sub_device_data[DEVICE_NAME_KEY]
        else:
            device_name = ""

        self._attr_has_entity_name = True
        self.device_name = device_name
        self.sensor_device_name = raw_device_data[DEVICE_NAME_KEY]
        self.device_id = device_id
        self.hub_id = hub_id
        self.sub_device_key = sub_device_key
        self.device_type = device_type
        self.raw_device_data = raw_device_data
        self._device = device
        self.entity_id = generate_entity_id(
            device_type, hub_id, device_id, sub_device_key
        )
        self._client = client
        self._attrs = _state_attributes(sub_device_data, device_type, sub_device_key)

        # devtype = raw_device_data["devtype"]
        if device_type in GAS_SENSOR_TYPES:
            if sub_device_key == "P1":
                self._device_class = SensorDeviceClass.GAS
            else:
                self._device_class = None
            self._unit = "None"
            self._state = sub_device_data.get("val")
        elif device_type in SMART_PLUG_TYPES and sub_device_key == "P2":
            self._device_class = SensorDeviceClass.ENERGY
            self._unit = UnitOfEnergy.KILO_WATT_HOUR
            self._state = sub_device_data["v"]
        elif device_type in SMART_PLUG_TYPES and sub_device_key == "P3":
            self._device_class = SensorDeviceClass.POWER
            self._unit = UnitOfPower.WATT
            self._state = sub_device_data["v"]
        elif device_type in CO2_SENSOR_TYPES:
            if sub_device_key == "P1":
                self._device_class = SensorDeviceClass.TEMPERATURE
                self._unit = UnitOfTemperature.CELSIUS
            elif sub_device_key == "P2":
                self._device_class = SensorDeviceClass.HUMIDITY
                self._unit = PERCENTAGE
            elif sub_device_key == "P3":
                self._device_class = SensorDeviceClass.CO2
                self._unit = CONCENTRATION_PARTS_PER_MILLION
            else:
                self._device_class = SensorDeviceClass.BATTERY
                self._unit = PERCENTAGE
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in ENV_SENSOR_TYPES:
            if sub_device_key == "T":
                self._device_class = SensorDeviceClass.TEMPERATURE
                self._unit = UnitOfTemperature.CELSIUS
            elif sub_device_key == "H":
                self._device_class = SensorDeviceClass.HUMIDITY
                self._unit = PERCENTAGE
            elif sub_device_key == "Z":
                self._device_class = SensorDeviceClass.ILLUMINANCE
                self._unit = LIGHT_LUX
            else:
                self._device_class = SensorDeviceClass.BATTERY
                self._unit = PERCENTAGE
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in TVOC_CO2_SENSOR_TYPES:
            if sub_device_key == "P1":
                self._device_class = SensorDeviceClass.TEMPERATURE
                self._unit = UnitOfTemperature.CELSIUS
            elif sub_device_key == "P2":
                self._device_class = SensorDeviceClass.HUMIDITY
                self._unit = PERCENTAGE
            elif sub_device_key == "P3":
                self._device_class = SensorDeviceClass.CO2
                self._unit = CONCENTRATION_PARTS_PER_MILLION
            elif sub_device_key == "P4":
                self._device_class = SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS
                self._unit = CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER
            elif sub_device_key == "P5":
                self._device_class = SensorDeviceClass.BATTERY
                self._unit = PERCENTAGE
            else:
                self._device_class = SensorDeviceClass.VOLTAGE
                self._unit = UnitOfElectricPotential.VOLT
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in DEFED_SENSOR_TYPES:
            if sub_device_key == "T":
                self._device_class = SensorDeviceClass.TEMPERATURE
                self._unit = UnitOfTemperature.CELSIUS
            else:
                self._device_class = SensorDeviceClass.BATTERY
                self._unit = PERCENTAGE
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in NOISE_SENSOR_TYPES:
            if sub_device_key == "P1":
                self._device_class = SensorDeviceClass.SOUND_PRESSURE
                self._unit = UnitOfSoundPressure.DECIBEL
            else:
                self._device_class = None
                self._unit = "None"
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type == "SL_SC_CM" and sub_device_key == "P3":
            self._device_class = SensorDeviceClass.BATTERY
            self._unit = PERCENTAGE
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in SMOKE_SENSOR_TYPES and sub_device_key == "P2":
            self._device_class = SensorDeviceClass.BATTERY
            self._unit = PERCENTAGE
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in ELECTRICITY_METER_TYPES and sub_device_key == "EPA":
            self._device_class = SensorDeviceClass.POWER
            self._unit = UnitOfPower.WATT
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in DLT_METER_TYPES:
            if sub_device_key == "EE":
                self._device_class = SensorDeviceClass.ENERGY
                self._unit = UnitOfEnergy.KILO_WATT_HOUR
            else:
                self._device_class = SensorDeviceClass.POWER
                self._unit = UnitOfPower.WATT
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in MODBUS_CONTROLLER_TYPES:
            self._device_class, self._unit = _modbus_sensor_metadata(sub_device_key)
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        elif device_type in AIR_PURIFIER_TYPES:
            if sub_device_key == "RM":
                self._device_class = SensorDeviceClass.ENUM
                self._unit = None
                self._attr_options = list(AIR_PURIFIER_MODES.values())
            elif sub_device_key == "T":
                self._device_class = SensorDeviceClass.TEMPERATURE
                self._unit = UnitOfTemperature.CELSIUS
            elif sub_device_key == "H":
                self._device_class = SensorDeviceClass.HUMIDITY
                self._unit = PERCENTAGE
            elif sub_device_key == "PM":
                self._device_class = SensorDeviceClass.PM25
                self._unit = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
            elif sub_device_key == "FL":
                self._device_class = SensorDeviceClass.DURATION
                self._unit = UnitOfTime.HOURS
            else:
                self._device_class = None
                self._unit = "None"
            self._state = _display_value(sub_device_data, device_type, sub_device_key)
        else:
            if sub_device_key in ("T", "P1") or (
                device_type in NATURE_TYPES and sub_device_key == "P4"
            ):
                self._device_class = SensorDeviceClass.TEMPERATURE
                self._unit = UnitOfTemperature.CELSIUS
            elif sub_device_key in ("H", "P2"):
                self._device_class = SensorDeviceClass.HUMIDITY
                self._unit = PERCENTAGE
            elif sub_device_key == "Z":
                self._device_class = SensorDeviceClass.ILLUMINANCE
                self._unit = LIGHT_LUX
            elif sub_device_key == "V":
                self._device_class = SensorDeviceClass.BATTERY
                self._unit = PERCENTAGE
            elif sub_device_key == "P5":
                self._device_class = SensorDeviceClass.VOLTAGE
                self._unit = UnitOfElectricPotential.VOLT
            elif sub_device_key == "P3":
                self._device_class = "None"
                self._unit = CONCENTRATION_PARTS_PER_MILLION
            elif sub_device_key == "P4":
                self._device_class = "None"
                self._unit = CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER
            elif sub_device_key == DIGITAL_DOORLOCK_BATTERY_EVENT_KEY:
                self._device_class = SensorDeviceClass.BATTERY
                self._unit = PERCENTAGE
            elif (
                device_type in LOCK_TYPES
                and sub_device_key == DIGITAL_DOORLOCK_OPERATION_EVENT_KEY
            ):
                self.device_name = "Operation Record"
                self._device_class = None
                self._unit = None
            else:
                self._unit = "None"
                self._device_class = "None"
            self._state = _display_value(sub_device_data, device_type, sub_device_key)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.hub_id, self.device_id)},
            name=self.sensor_device_name,
            manufacturer=MANUFACTURER,
            model=self.device_type,
            sw_version=self.raw_device_data[DEVICE_VERSION_KEY],
            via_device=(DOMAIN, self.hub_id),
        )

    @property
    def device_class(self):
        """Return the device class of this entity."""
        return self._device_class

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unique_id(self):
        """A unique identifier for this entity."""
        return self.entity_id

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{self.entity_id}",
                self._update_value,
            )
        )

    async def _update_value(self, data) -> None:
        if data is not None:
            self._state = _display_value(data, self.device_type, self.sub_device_key)
            self._attrs = _state_attributes(
                data, self.device_type, self.sub_device_key
            )
            self.schedule_update_ha_state()

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attrs


def _display_value(data, device_type=None, sub_device_key=None):
    """Return the display value, falling back to raw tenths for temperature."""
    if "v" in data:
        return data["v"]
    if (
        device_type in CO2_SENSOR_TYPES
        and sub_device_key == "P3"
        or device_type in NOISE_SENSOR_TYPES
    ):
        return data.get("val")
    if device_type in ENV_SENSOR_TYPES and sub_device_key == "Z":
        return data.get("val")
    if device_type in TVOC_CO2_SENSOR_TYPES:
        if sub_device_key == "P3":
            return data.get("val")
        if sub_device_key == "P4":
            return data.get("val") / 1000 if "val" in data else None
    if device_type in ELECTRICITY_METER_TYPES:
        return data.get("val")
    if device_type in DLT_METER_TYPES:
        return _display_float_value(data)
    if device_type in MODBUS_CONTROLLER_TYPES:
        if sub_device_key in ["T", "H"]:
            return data["v"] if "v" in data else data.get("val") / 10
        if sub_device_key in ["PM", "PHM", "SMOKE"]:
            return data.get("val")
        return _display_float_value(data)
    if device_type in AIR_PURIFIER_TYPES:
        if sub_device_key == "RM":
            return AIR_PURIFIER_MODES.get(data.get("val"), f"unknown_{data.get('val')}")
        if sub_device_key in ["PM", "FL", "UV"]:
            return data.get("val")
    if device_type in LOCK_TYPES and sub_device_key == DIGITAL_DOORLOCK_BATTERY_EVENT_KEY:
        return data.get("val")
    if device_type in LOCK_TYPES and sub_device_key == DIGITAL_DOORLOCK_OPERATION_EVENT_KEY:
        return data.get("val")
    if "val" in data:
        return data["val"] / 10
    return None


def _display_float_value(data):
    """Return friendly value, decoding raw IEEE-754 integers when needed."""
    if "v" in data:
        return data["v"]
    if "val" not in data:
        return None
    return _float32_from_int(data["val"])


def _float32_from_int(value):
    """Decode a raw unsigned 32-bit IEEE-754 integer."""
    return struct.unpack("!f", int(value).to_bytes(4, "big", signed=False))[0]


def _is_modbus_sensor_key(sub_device_key):
    """Return true for documented V_485_P sensor IO keys."""
    if sub_device_key in MODBUS_SENSOR_KEYS:
        return True
    return (
        sub_device_key.startswith(("EE", "EP", "EPF", "EF", "EI", "EV"))
        and sub_device_key[-1].isdigit()
        or sub_device_key.startswith("PM")
        and sub_device_key[2:].isdigit()
    )


def _modbus_sensor_metadata(sub_device_key):
    """Return Home Assistant metadata for a V_485_P sensor IO key."""
    if sub_device_key.startswith("EE"):
        return SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR
    if sub_device_key.startswith("EPF"):
        return SensorDeviceClass.POWER_FACTOR, None
    if sub_device_key.startswith("EP"):
        return SensorDeviceClass.POWER, UnitOfPower.WATT
    if sub_device_key.startswith("EF"):
        return SensorDeviceClass.FREQUENCY, UnitOfFrequency.HERTZ
    if sub_device_key.startswith("EI"):
        return SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE
    if sub_device_key.startswith("EV"):
        return SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT
    if sub_device_key == "T":
        return SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS
    if sub_device_key == "H":
        return SensorDeviceClass.HUMIDITY, PERCENTAGE
    if sub_device_key == "PM":
        return SensorDeviceClass.PM25, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    if sub_device_key.startswith("PM"):
        return SensorDeviceClass.PM10, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    if sub_device_key == "COPPM":
        return SensorDeviceClass.CO, CONCENTRATION_PARTS_PER_MILLION
    if sub_device_key == "CO2PPM":
        return SensorDeviceClass.CO2, CONCENTRATION_PARTS_PER_MILLION
    if sub_device_key == "TVOC":
        return (
            SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
            CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER,
        )
    if sub_device_key == "PHM":
        return SensorDeviceClass.SOUND_PRESSURE, UnitOfSoundPressure.DECIBEL
    if sub_device_key in ["CH2OPPM", "NH3PPM", "H2SPPM", "SMOKE"]:
        return SensorDeviceClass.GAS, CONCENTRATION_PARTS_PER_MILLION
    if sub_device_key == "O2VOL":
        return SensorDeviceClass.GAS, PERCENTAGE
    return None, "None"


def _state_attributes(data, device_type=None, sub_device_key=None):
    """Return useful raw attributes for compound LifeSmart sensor values."""
    attrs = {}
    if device_type in GAS_SENSOR_TYPES and sub_device_key == "P1":
        attrs["alarm"] = data.get("type", 0) % 2 == 1
    elif device_type in NOISE_SENSOR_TYPES and sub_device_key == "P1":
        attrs["alarm"] = data.get("type", 0) % 2 == 1
    elif (
        device_type in LOCK_TYPES
        and sub_device_key == DIGITAL_DOORLOCK_OPERATION_EVENT_KEY
    ):
        attrs.update(_doorlock_operation_attributes(data))

    if "val" in data:
        attrs["raw"] = data["val"]
    return attrs


def _doorlock_operation_attributes(data):
    """Decode documented digital door lock operation record fields."""
    val = data.get("val")
    if val is None:
        return {}

    record_type = None
    user_id = None
    user_flag = None
    value_length = _doorlock_operation_value_length(data)
    if value_length == 8:
        record_type = val
    elif value_length == 24:
        record_type = (val >> 16) & 0xFF
        user_id = val & 0xFFFF
    else:
        record_type = (val >> 24) & 0xFF
        user_id = (val >> 8) & 0xFFFF
        user_flag = val & 0xFF

    attrs = {"record_type": record_type}
    if user_id is not None:
        attrs["user_id"] = user_id
    if user_flag is not None:
        attrs["user_flag"] = user_flag
        attrs["user_role"] = _doorlock_operation_user_role(user_flag)
    return attrs


def _doorlock_operation_value_length(data):
    """Return documented operation value bit length."""
    type_value = data.get("type")
    if type_value == 0x4E:
        return 8
    if type_value in [0x5E, 0x6E]:
        return 24
    if type_value == 0x7E:
        return 32

    val = data.get("val", 0)
    if val <= 0xFF:
        return 8
    if val <= 0xFFFFFF:
        return 24
    return 32


def _doorlock_operation_user_role(user_flag):
    """Return documented operation record user role from low two bits."""
    match user_flag & 0b11:
        case 0b11:
            return "administrator"
        case 0b01:
            return "common_user"
        case 0b00:
            return "deleted_user"
        case _:
            return "unknown"
