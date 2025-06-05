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
    DEVICE_DATA_KEY,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DIGITAL_DOORLOCK_ALARM_EVENT_KEY,
    DIGITAL_DOORLOCK_LOCK_EVENT_KEY,
    DOMAIN,
    GENERIC_CONTROLLER_TYPES,
    GUARD_SENSOR_TYPES,
    HUB_ID_KEY,
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    LOCK_TYPES,
    MANUFACTURER,
    MOTION_SENSOR_TYPES,
    SUBDEVICE_INDEX_KEY,
)

_LOGGER = logging.getLogger(__name__)


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

        if device_type not in BINARY_SENSOR_TYPES + LOCK_TYPES:
            continue

        ha_device = LifeSmartDevice(
            device,
            client,
        )
        for sub_device_key in device[DEVICE_DATA_KEY]:
            sub_device_data = device[DEVICE_DATA_KEY][sub_device_key]
            if device_type in GENERIC_CONTROLLER_TYPES:
                if sub_device_key in [
                    "P5",
                    "P6",
                    "P7",
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
        # self._attrs = sub_device_data

        if device_type in GUARD_SENSOR_TYPES:
            if sub_device_key in ["G"]:
                self._device_class = BinarySensorDeviceClass.DOOR
                if sub_device_data["val"] == 0:
                    self._state = True
                else:
                    self._state = False
            if sub_device_key in ["AXS"]:
                self._device_class = BinarySensorDeviceClass.VIBRATION
                if sub_device_data["val"] == 0:
                    self._state = False
                else:
                    self._state = True
            if sub_device_key in ["B"]:
                self._device_class = None
                if sub_device_data["val"] == 0:
                    self._state = False
                else:
                    self._state = True
        elif device_type in MOTION_SENSOR_TYPES:
            self._device_class = BinarySensorDeviceClass.MOTION
            if sub_device_data["val"] == 0:
                self._state = False
            else:
                self._state = True
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
            # On means problem detected, Off means no problem (OK)
            val = sub_device_data["val"]
            if val > 0:
                self._state = True
            else:
                self._state = False
            self._attrs = {"raw": val}

        elif device_type in GENERIC_CONTROLLER_TYPES:
            self._attrs = sub_device_data
            self._device_class = BinarySensorDeviceClass.LOCK
            # On means open (unlocked), Off means closed (locked)
            if sub_device_data["val"] == 0:
                self._state = True
            else:
                self._state = False
        else:
            self._device_class = BinarySensorDeviceClass.SMOKE
            if sub_device_data["val"] == 0:
                self._state = False
            else:
                self._state = True

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
                f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{self.entity_id}",
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
        else:
            if data["val"] == 0:
                self._state = True
            else:
                self._state = False
            self.schedule_update_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return self._attrs


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

    unlock_method_code = data["val"] >> 12
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
    return data["type"] % 2 == 1


def get_doorlock_unlocking_user(data):
    """Get user id of who trying to unlock."""
    val = data["val"]
    unlocking_user = val & 0xFFF
    return unlocking_user


def build_doorlock_attribute(data):
    """Build an attribute for digital door lock."""
    unlocking_user_id = get_doorlock_unlocking_user(data)

    return {
        "unlocking_method": extract_doorlock_unlocking_method(data),
        "unlocking_user": unlocking_user_id,
    }
