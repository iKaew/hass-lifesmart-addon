"""Support for LifeSmart binary sensors."""
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from . import LifeSmartDevice, generate_entity_id
from .const import (
    BINARY_SENSOR_TYPES,
    DEFED_DOOR_SENSOR_TYPES,
    DEFED_KEYFOB_TYPES,
    DEFED_MOTION_SENSOR_TYPES,
    DEFED_SENSOR_TYPES,
    DEFED_SIREN_TYPES,
    DEVICE_DATA_KEY,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DIGITAL_DOORLOCK_ALARM_EVENT_KEY,
    DIGITAL_DOORLOCK_DOORBELL_EVENT_KEY,
    DIGITAL_DOORLOCK_LOCK_EVENT_KEY,
    DOMAIN,
    GAS_SENSOR_TYPES,
    GENERIC_CONTROLLER_BINARY_PORTS,
    GENERIC_CONTROLLER_TYPES,
    GUARD_SENSOR_TYPES,
    HUB_ID_KEY,
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    LOCK_TYPES,
    MANUFACTURER,
    MOTION_SENSOR_TYPES,
    NOISE_SENSOR_TYPES,
    RADAR_MOTION_SENSOR_TYPES,
    SMART_ALARM_TYPES,
    SMART_CAMERA_STATUS_BINARY_KEYS,
    SMART_CAMERA_STATUS_EVENT_KEY,
    SMART_CAMERA_STATUS_EXTERNAL_POWER_KEY,
    SMART_CAMERA_STATUS_ROTARY_PTZ_KEY,
    SMART_CAMERA_STATUS_ROTATING_KEY,
    SMART_CAMERA_TYPES,
    SPOT_IR_TYPES,
    SUBDEVICE_INDEX_KEY,
    WATER_LEAK_SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)

SMART_CAMERA_STATUS_BIT_CONFIG = {
    SMART_CAMERA_STATUS_EXTERNAL_POWER_KEY: {
        "bit": 0,
        "name": "External Power",
        "device_class": BinarySensorDeviceClass.POWER,
    },
    SMART_CAMERA_STATUS_ROTARY_PTZ_KEY: {
        "bit": 1,
        "name": "Rotary PTZ",
        "device_class": None,
    },
    SMART_CAMERA_STATUS_ROTATING_KEY: {
        "bit": 2,
        "name": "Rotating",
        "device_class": BinarySensorDeviceClass.MOVING,
    },
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Initialzie Switch entities for HA."""
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

        supported_binary_sensor_types = (
            BINARY_SENSOR_TYPES
            + LOCK_TYPES
            + WATER_LEAK_SENSOR_TYPES
            + RADAR_MOTION_SENSOR_TYPES
            + DEFED_SENSOR_TYPES
            + GAS_SENSOR_TYPES
            + NOISE_SENSOR_TYPES
            + SMART_ALARM_TYPES
            + SMART_CAMERA_TYPES
            + SPOT_IR_TYPES
        )
        if device_type not in supported_binary_sensor_types:
            continue

        ha_device = LifeSmartDevice(
            device,
            client,
        )
        for sub_device_key in device[DEVICE_DATA_KEY]:
            sub_device_data = device[DEVICE_DATA_KEY][sub_device_key]
            if device_type in GENERIC_CONTROLLER_TYPES:
                if sub_device_key in GENERIC_CONTROLLER_BINARY_PORTS:
                    sensor_devices.append(
                        LifeSmartBinarySensor(
                            ha_device,
                            device,
                            sub_device_key,
                            sub_device_data,
                            client,
                        )
                    )
            elif device_type in SPOT_IR_TYPES and sub_device_key == "P2":
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif (
                device_type in LOCK_TYPES
                and sub_device_key == DIGITAL_DOORLOCK_LOCK_EVENT_KEY
            ):  # noqa: SIM114
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif (
                device_type in LOCK_TYPES
                and sub_device_key == DIGITAL_DOORLOCK_ALARM_EVENT_KEY
            ):  # noqa: SIM114
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif (
                device_type in LOCK_TYPES
                and sub_device_key == DIGITAL_DOORLOCK_DOORBELL_EVENT_KEY
            ):  # noqa: SIM114
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in BINARY_SENSOR_TYPES and sub_device_key in [
                "M",
                "G",
                "B",
                "AXS",
                "P1",
            ]:
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in WATER_LEAK_SENSOR_TYPES and sub_device_key == "WA":
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in RADAR_MOTION_SENSOR_TYPES and sub_device_key == "P1":
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in DEFED_DOOR_SENSOR_TYPES and sub_device_key in [
                "GA",
                "A2",
                "TR",
            ]:
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in DEFED_MOTION_SENSOR_TYPES and sub_device_key in [
                "M",
                "TR",
            ]:
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in DEFED_SIREN_TYPES and sub_device_key in ["SR", "TR"]:
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in DEFED_KEYFOB_TYPES and sub_device_key in [
                "eB1",
                "eB2",
                "eB3",
                "eB4",
            ]:
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in GAS_SENSOR_TYPES and sub_device_key == "P3":
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in NOISE_SENSOR_TYPES and sub_device_key == "P3":
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in SMART_ALARM_TYPES and sub_device_key in ["P1", "P2"]:
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif device_type in SMART_CAMERA_TYPES and sub_device_key == "M":
                sensor_devices.append(
                    LifeSmartBinarySensor(
                        ha_device,
                        device,
                        sub_device_key,
                        sub_device_data,
                        client,
                    )
                )
            elif (
                device_type in SMART_CAMERA_TYPES
                and sub_device_key == SMART_CAMERA_STATUS_EVENT_KEY
            ):
                for status_key in SMART_CAMERA_STATUS_BINARY_KEYS:
                    sensor_devices.append(
                        LifeSmartBinarySensor(
                            ha_device,
                            device,
                            status_key,
                            sub_device_data,
                            client,
                        )
                    )
    async_add_entities(sensor_devices)


class LifeSmartBinarySensor(BinarySensorEntity):
    """Representation of LifeSmartBinarySensor."""

    def __init__(  # noqa: D107
        self, device, raw_device_data, sub_device_key, sub_device_data, client
    ) -> None:
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
        self.sensor_device_name = raw_device_data[DEVICE_NAME_KEY]
        self.device_name = device_name
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
        self._attrs = {}

        if device_type in GUARD_SENSOR_TYPES:
            if sub_device_key in ["G"]:
                self._device_class = BinarySensorDeviceClass.DOOR
                self._state = sub_device_data["val"] == 0
            if sub_device_key in ["AXS"]:
                self._device_class = BinarySensorDeviceClass.VIBRATION
                self._state = sub_device_data["val"] != 0
            if sub_device_key in ["B"]:
                self._device_class = None
                self._state = sub_device_data["val"] != 0
        elif device_type in MOTION_SENSOR_TYPES:
            self._device_class = BinarySensorDeviceClass.MOTION
            self._state = sub_device_data["val"] != 0
        elif device_type in RADAR_MOTION_SENSOR_TYPES:
            self._device_class = BinarySensorDeviceClass.MOTION
            self._state = sub_device_data["val"] != 0
        elif device_type in WATER_LEAK_SENSOR_TYPES:
            self._device_class = BinarySensorDeviceClass.MOISTURE
            self._state = sub_device_data["val"] != 0
        elif device_type in DEFED_DOOR_SENSOR_TYPES:
            if sub_device_key == "GA":
                self._device_class = BinarySensorDeviceClass.DOOR
            elif sub_device_key == "A2":
                self._device_class = BinarySensorDeviceClass.OPENING
            else:
                self._device_class = BinarySensorDeviceClass.TAMPER
            self._state = sub_device_data.get("type", 0) % 2 == 1
        elif device_type in DEFED_MOTION_SENSOR_TYPES:
            if sub_device_key == "M":
                self._device_class = BinarySensorDeviceClass.MOTION
            else:
                self._device_class = BinarySensorDeviceClass.TAMPER
            self._state = sub_device_data.get("type", 0) % 2 == 1
        elif device_type in DEFED_SIREN_TYPES:
            if sub_device_key == "SR":
                self._device_class = BinarySensorDeviceClass.SOUND
            else:
                self._device_class = BinarySensorDeviceClass.TAMPER
            self._state = sub_device_data.get("type", 0) % 2 == 1
        elif device_type in DEFED_KEYFOB_TYPES:
            self._device_class = None
            self._state = sub_device_data.get("type", 0) % 2 == 1
        elif device_type in GAS_SENSOR_TYPES:
            self._device_class = BinarySensorDeviceClass.SOUND
            self._state = sub_device_data.get("type", 0) % 2 == 1
        elif device_type in NOISE_SENSOR_TYPES:
            self._device_class = BinarySensorDeviceClass.SOUND
            self._state = sub_device_data.get("type", 0) % 2 == 1
        elif device_type in SMART_ALARM_TYPES:
            self._device_class = BinarySensorDeviceClass.SOUND
            self._state = sub_device_data.get("type", 0) % 2 == 1
        elif device_type in SMART_CAMERA_TYPES:
            if sub_device_key == "M":
                self._device_class = BinarySensorDeviceClass.MOTION
                self._state = sub_device_data.get("val", 0) != 0
            else:
                config = SMART_CAMERA_STATUS_BIT_CONFIG[sub_device_key]
                self.device_name = config["name"]
                self._device_class = config["device_class"]
                self._state = _camera_status_bit_state(sub_device_data, sub_device_key)
                self._attrs = {"raw": sub_device_data.get("val")}
        elif device_type in SPOT_IR_TYPES:
            self._device_class = None
            self._state = sub_device_data.get("type", 0) % 2 == 1
            self._attrs = {"raw": sub_device_data.get("val")}
        elif (
            device_type in LOCK_TYPES
            and sub_device_key == DIGITAL_DOORLOCK_LOCK_EVENT_KEY
        ):
            self.device_name = "Status"
            self._device_class = BinarySensorDeviceClass.LOCK
            self._state = is_doorlock_unlocked(sub_device_data)
            self._attrs = build_doorlock_attribute(sub_device_data)
        elif (
            device_type in LOCK_TYPES
            and sub_device_key == DIGITAL_DOORLOCK_ALARM_EVENT_KEY
        ):
            self.device_name = "Alarm"
            self._device_class = BinarySensorDeviceClass.PROBLEM
            self._state = sub_device_data["val"] > 0
            self._attrs = build_doorlock_alarm_attribute(sub_device_data)
        elif (
            device_type in LOCK_TYPES
            and sub_device_key == DIGITAL_DOORLOCK_DOORBELL_EVENT_KEY
        ):
            self.device_name = "Doorbell"
            self._device_class = BinarySensorDeviceClass.SOUND
            self._state = sub_device_data["type"] % 2 == 1
            self._attrs = {"raw": sub_device_data.get("val")}
        elif device_type in GENERIC_CONTROLLER_TYPES:
            self._attrs = sub_device_data
            self._device_class = BinarySensorDeviceClass.LOCK
            self._state = _generic_controller_binary_state(
                sub_device_data, device_type
            )
        else:
            self._device_class = BinarySensorDeviceClass.SMOKE
            self._state = sub_device_data["val"] != 0

    @property
    def name(self):
        """Name of the entity."""
        return self.device_name

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.hub_id, self.device_id)},
            name=self.sensor_device_name,
            manufacturer=MANUFACTURER,
            model=self.device_type,
            sw_version=self.raw_device_data["ver"],
            via_device=(DOMAIN, self.hub_id),
        )

    @property
    def is_on(self):
        """Return true if sensor is on."""
        return self._state

    @property
    def device_class(self):
        """Return the class of binary sensor."""
        return self._device_class

    @property
    def unique_id(self):
        """A unique identifier for this entity."""
        return self.entity_id

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{self._signal_entity_id}",
                self._update_state,
            )
        )

    async def _update_state(self, data) -> None:
        if data is None:
            return

        device_type = data[DEVICE_TYPE_KEY]
        sub_device_key = data[SUBDEVICE_INDEX_KEY]

        if (
            device_type in LOCK_TYPES
            and sub_device_key == DIGITAL_DOORLOCK_LOCK_EVENT_KEY
        ):
            self._state = is_doorlock_unlocked(data)
            self._attrs = build_doorlock_attribute(data)
            self.schedule_update_ha_state()

            _LOGGER.debug(self._attrs)
        elif (
            device_type in LOCK_TYPES
            and sub_device_key == DIGITAL_DOORLOCK_ALARM_EVENT_KEY
        ):
            self._state = data.get("val", 0) > 0
            self._attrs = build_doorlock_alarm_attribute(data)
            self.schedule_update_ha_state()
        else:
            self._state = self._state_from_data(data)
            self.schedule_update_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return self._attrs

    def _state_from_data(self, data) -> bool:
        """Return the binary sensor state for the LifeSmart device event."""
        device_type = data[DEVICE_TYPE_KEY]
        sub_device_key = data[SUBDEVICE_INDEX_KEY]
        val = data.get("val", 0)

        if device_type in GUARD_SENSOR_TYPES and sub_device_key == "G":
            return val == 0
        if device_type in GENERIC_CONTROLLER_TYPES:
            return _generic_controller_binary_state(data, device_type)
        if device_type in SPOT_IR_TYPES:
            return data.get("type", 0) % 2 == 1
        if device_type in DEFED_SENSOR_TYPES:
            return data.get("type", 0) % 2 == 1
        if (
            device_type in GAS_SENSOR_TYPES
            or device_type in NOISE_SENSOR_TYPES
            or device_type in SMART_ALARM_TYPES
        ):
            return data.get("type", 0) % 2 == 1
        if device_type in SMART_CAMERA_TYPES:
            if self.sub_device_key == "M":
                return val != 0
            return _camera_status_bit_state(data, self.sub_device_key)
        if (
            device_type in LOCK_TYPES
            and sub_device_key == DIGITAL_DOORLOCK_DOORBELL_EVENT_KEY
        ):
            return data.get("type", 0) % 2 == 1
        if (
            device_type in LOCK_TYPES
            and sub_device_key == DIGITAL_DOORLOCK_ALARM_EVENT_KEY
        ):
            return val > 0
        return val != 0

    @property
    def _signal_entity_id(self):
        """Return the dispatcher signal entity id for this binary sensor."""
        return self.entity_id


def _camera_status_bit_state(data, sub_device_key):
    """Return one decoded LifeSmart camera status bit."""
    config = SMART_CAMERA_STATUS_BIT_CONFIG[sub_device_key]
    return bool(data.get("val", 0) & (1 << config["bit"]))


def extract_doorlock_unlocking_method(data):
    """Convert unlock code to meaningful text."""
    """Unlocking method: (
                0: undefined;
                1: Password;
                2: Fingerprint;
                3: NFC;
                4: Mechanical key;
                5: Remote unlocking;
                6: One-button opening (12V unlocking signal turns on
                Lock);
                7: APP is opened;
                8: Bluetooth unlocking;
                9: Manual unlock;
                15: Error)
    """

    unlock_method_code = _doorlock_unlock_value(data) >> 12
    match unlock_method_code:
        case 1:
            return "Password"
        case 2:
            return "Fingerprint"
        case 3:
            return "NFC"
        case 4:
            return "Mechanical key"
        case 5:
            return "Remote unlocking"
        case 6:
            return "One-button opening"
        case 7:
            return "APP"
        case 8:
            return "Bluetooth unlocking"
        case 9:
            return "Manual unlock"
        case 15:
            return "Error"
        case _:
            return "Undefined"


def is_doorlock_unlocked(data):
    """Check if the door is in unlocking state."""
    if "type" in data:
        try:
            return int(str(data["type"]), 0) % 2 == 1
        except (TypeError, ValueError):
            return False
    return _doorlock_unlock_value(data) != 0


def get_doorlock_unlocking_user(data):
    """Get user id of who trying to unlock."""
    val = _doorlock_unlock_value(data)
    unlocking_user = val & 0xFFF
    return unlocking_user


def build_doorlock_attribute(data):
    """Build an attribute for digital door lock."""
    unlocking_user_id = get_doorlock_unlocking_user(data)

    return {
        "unlocking_method": extract_doorlock_unlocking_method(data),
        "unlocking_user": unlocking_user_id,
    }


def _doorlock_unlock_value(data):
    """Return the raw digital door lock unlock value."""
    return data.get("val", data.get("v", 0))


def build_doorlock_alarm_attribute(data):
    """Build decoded alarm attributes for digital door lock alarm reports."""
    val = data.get("val", data.get("v", 0))
    return {
        "raw": val,
        "error_alarm": bool(val & (1 << 0)),
        "duress_alarm": bool(val & (1 << 1)),
        "lock_pick_alarm": bool(val & (1 << 2)),
        "mechanical_key_alarm": bool(val & (1 << 3)),
        "low_battery_alarm": bool(val & (1 << 4)),
        "exception_alarm": bool(val & (1 << 5)),
        "doorbell": bool(val & (1 << 6)),
        "fire_alarm": bool(val & (1 << 7)),
        "intrusion_alarm": bool(val & (1 << 8)),
        "keep_open": bool(val & (1 << 10)),
        "factory_reset_alarm": bool(val & (1 << 11)),
    }


def _generic_controller_binary_state(data, device_type=None):
    """Return documented general controller input trigger state."""
    if device_type == "SL_P":
        return data.get("val", 1) == 0
    if "type" in data:
        return data["type"] % 2 == 1
    return data.get("val", 1) == 0
