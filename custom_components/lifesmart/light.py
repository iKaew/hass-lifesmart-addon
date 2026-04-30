"""Support for LifeSmart Gateway Light."""

import binascii
import logging
import struct

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ColorMode,
    # SUPPORT_BRIGHTNESS,
    # SUPPORT_COLOR,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
import homeassistant.util.color as color_util

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
    QUANTUM_TYPES,
    SPOT_LIGHT_TYPES,
    SPOT_TYPES,
)

_LOGGER = logging.getLogger(__name__)

LIGHT_DIMMER_TYPES = [
    "SL_LI_WW",
]

MAX_MIREDS = int(1000000 / 2700)
MIN_MIREDS = int(1000000 / 6500)

DYN_EFFECTS = {
    "Grass": 0x8218CC80,
    "Sea wave": 0x8318CC80,
    "Deep-blue mountains": 0x8418CC80,
    "Flirtatious purple": 0x8518CC80,
    "Raspberry": 0x8618CC80,
    "Orange": 0x8718CC80,
    "Autumn fruit": 0x8818CC80,
    "Ice cream": 0x8918CC80,
    "Plateau": 0x8020CC80,
    "Pizza": 0x8120CC80,
    "Fruit juice": 0x8A20CC80,
    "Warm cottage": 0x8B30CC80,
    "Magic red": 0x9318CC80,
    "Light spot": 0x9518CC80,
    "Blue": 0x9718CC80,
    "First rays of the morning sun": 0x9618CC80,
    "Hibiscus": 0x9818CC80,
    "Colorful era": 0x9918CC80,
    "Sky world": 0xA318CC80,
    "Charm blue": 0xA718CC80,
    "Bright red": 0xA918CC80,
}
DYN_EFFECT_NAMES_BY_VALUE = {value: name for name, value in DYN_EFFECTS.items()}


def _is_on_type(value) -> bool:
    """Return True when a LifeSmart type value represents on."""
    try:
        return int(str(value), 0) % 2 == 1
    except (TypeError, ValueError):
        return False


def _effect_from_dyn_value(value):
    """Return a Home Assistant effect name for a LifeSmart DYN value."""
    try:
        dyn_value = int(value)
    except (TypeError, ValueError):
        return None
    return DYN_EFFECT_NAMES_BY_VALUE.get(dyn_value, f"DYN 0x{dyn_value:08x}")


def _dyn_value_from_effect(effect):
    """Return a LifeSmart DYN value for a Home Assistant effect name."""
    if effect in DYN_EFFECTS:
        return DYN_EFFECTS[effect]
    try:
        return int(str(effect), 0)
    except ValueError:
        return None


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Perform the setup for LifeSmart lights devices."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    exclude_devices = hass.data[DOMAIN][config_entry.entry_id]["exclude_devices"]
    exclude_hubs = hass.data[DOMAIN][config_entry.entry_id]["exclude_hubs"]
    client = hass.data[DOMAIN][config_entry.entry_id]["client"]
    light_devices = []
    for device in devices:
        if (
            device[DEVICE_ID_KEY] in exclude_devices
            or device[HUB_ID_KEY] in exclude_hubs
        ):
            continue

        device_type = device[DEVICE_TYPE_KEY]
        ha_device = LifeSmartDevice(
            device,
            client,
        )
        # P1,P2,P3 info packed into one data for one entity
        if device_type in LIGHT_DIMMER_TYPES:
            light_devices.append(
                LifeSmartLight(
                    ha_device,
                    device,
                    "P1P2",
                    device[DEVICE_DATA_KEY],
                    client,
                )
            )
        elif device_type == "MSL_IRCTL":
            if "RGBW" in device[DEVICE_DATA_KEY]:
                light_devices.append(
                    LifeSmartLight(
                        ha_device,
                        device,
                        "RGBW",
                        device[DEVICE_DATA_KEY]["RGBW"],
                        client,
                    )
                )
            elif "RGB" in device[DEVICE_DATA_KEY]:
                light_devices.append(
                    LifeSmartSLSPOTLight(
                        ha_device,
                        device,
                        "RGB",
                        device[DEVICE_DATA_KEY]["RGB"],
                        client,
                    )
                )
        elif device_type in SPOT_LIGHT_TYPES and "RGB" in device[DEVICE_DATA_KEY]:
            light_devices.append(  # noqa: PERF401
                LifeSmartSLSPOTLight(
                    ha_device,
                    device,
                    "RGB",
                    device[DEVICE_DATA_KEY]["RGB"],
                    client,
                )
            )
        elif device_type in QUANTUM_TYPES:
            if "P2" in device[DEVICE_DATA_KEY]:
                light_devices.append(
                    LifeSmartLight(
                        ha_device,
                        device,
                        "P2",
                        device[DEVICE_DATA_KEY]["P2"],
                        client,
                    )
                )
        else:
            for sub_device_key in device[DEVICE_DATA_KEY]:
                if sub_device_key in [
                    "RGB",
                    "RGBW",
                    "dark",
                    "dark1",
                    "dark2",
                    "dark3",
                    "bright",
                    "bright1",
                    "bright2",
                    "bright3",
                ]:
                    light_devices.append(  # noqa: PERF401
                        LifeSmartLight(
                            ha_device,
                            device,
                            sub_device_key,
                            device[DEVICE_DATA_KEY][sub_device_key],
                            client,
                        )
                    )

    async_add_entities(light_devices)


class LifeSmartSLSPOTLight(LightEntity):
    """Representation of a LifeSmart SL SPOT."""

    def __init__(
        self, device, raw_device_data, sub_device_key, sub_device_data, client
    ) -> None:
        """Initialize the light."""

        self._attr_has_entity_name = True
        self._device_name = raw_device_data.get(DEVICE_NAME_KEY, "")
        self.name = "Light"
        self._device_type = raw_device_data[DEVICE_TYPE_KEY]
        self._device_id = raw_device_data[DEVICE_ID_KEY]
        self._hub_id = raw_device_data[HUB_ID_KEY]
        self._sub_device_key = sub_device_key
        self._sw_version = raw_device_data.get(DEVICE_VERSION_KEY)
        self._attributes = {}

        self._raw_device_data = raw_device_data
        self._device = device
        self._client = client
        self._entity_id = generate_entity_id(
            self._device_type, self._hub_id, self._device_id, self._sub_device_key
        )

        self._brightness = None
        self._color_temp = None
        _LOGGER.info("Light: %s added", str(self.entity_id))
        _LOGGER.info("Light: sub_device_key: %s ", str(sub_device_key))
        _LOGGER.info("Light: sub_device_data: %s ", str(sub_device_data))

        if _is_on_type(sub_device_data.get("type")):
            self._state = True
            self._brightness = 255
        else:
            self._state = False

        self._color_mode = ColorMode.RGB
        self._supported_color_modes = {ColorMode.RGB}
        self._max_mireds = None
        self._min_mireds = None

        # convert from wrgb to rgbw tuple
        self._rgb_color = self.convert_LS_wrgb_to_HA_rgb(sub_device_data["val"])
        _LOGGER.debug("rgb: %s", str(self._rgb_color))

        super().__init__()

    def convert_HA_rgb_to_LS_wrgb(self, rgb_color) -> int:  # noqa: D102
        rgbhex = (0, *rgb_color)
        rgbhex = binascii.hexlify(struct.pack("BBBB", *rgbhex)).decode("ASCII")
        return int(rgbhex, 16)

    def convert_LS_wrgb_to_HA_rgb(self, value: int) -> tuple:  # noqa: D102
        # convert from wrgb to rgbw tuple
        rgbhexstr = f"{value:x}"
        rgbhexstr = rgbhexstr.zfill(8)
        rgbhex = bytes.fromhex(rgbhexstr[2:])
        return struct.unpack("BBB", rgbhex)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub_id, self._device_id)},
            name=self._device_name,
            manufacturer=MANUFACTURER,
            model=self._device_type,
            sw_version=self._sw_version,
            via_device=(DOMAIN, self._hub_id),
        )

    async def _update_state(self, data) -> None:
        if data is None:
            return
        if _is_on_type(data.get("type")):
            self._state = True
            self._brightness = 255
        else:
            self._state = False

        # convert from wrgb to rgbw tuple
        self._rgb_color = self.convert_LS_wrgb_to_HA_rgb(data["val"])
        _LOGGER.debug("rgb: %s", str(self._rgb_color))
        self.schedule_update_ha_state()

    async def async_added_to_hass(self):
        """Add to Hass."""
        # register call back for msg update
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{self.entity_id}",
                self._update_state,
            )
        )

        rmdata = {}
        rmlist = await self._client.get_ir_remote_list_async(self._hub_id)
        for device_id in rmlist:
            if self._device_id in device_id:
                rms = await self._client.get_ir_remote_async(self._hub_id, device_id)
                rms["category"] = rmlist[device_id]["category"]
                rms["brand"] = rmlist[device_id]["brand"]
                rms["idx"] = rmlist[device_id]["idx"]
                rmdata[device_id] = rms
        _LOGGER.debug("Remote List: %s", str(rmdata))
        self._attributes["remotelist"] = rmdata

    async def async_turn_on(self, **kwargs):
        """Turn the light on."""
        if ATTR_RGB_COLOR in kwargs:
            self._rgb_color = kwargs[ATTR_RGB_COLOR]
            rgbhex = self.convert_HA_rgb_to_LS_wrgb(self._rgb_color)

            await self._client.send_epset_async(
                "0xff",
                rgbhex,
                self._sub_device_key,
                self._hub_id,
                self._device_id,
            )
        elif ATTR_BRIGHTNESS in kwargs:
            rgbhex = self.convert_HA_rgb_to_LS_wrgb(self._rgb_color)
            await self._client.send_epset_async(
                "0xff",
                rgbhex,
                self._sub_device_key,
                self._hub_id,
                self._device_id,
            )

        else:
            await self._client.turn_on_light_swith_async(
                self._sub_device_key, self._hub_id, self._device_id
            )
        self._state = True

    async def async_turn_off(self, **kwargs):
        """Turn the light off."""
        if ATTR_RGB_COLOR in kwargs:
            self._rgb_color = kwargs[ATTR_RGB_COLOR]
            rgbhex = self.convert_HA_rgb_to_LS_wrgb(self._rgb_color)
            await self._client.send_epset_async(
                "0xfe",
                rgbhex,
                self._sub_device_key,
                self._hub_id,
                self._device_id,
            )
        else:
            await self._client.turn_off_light_swith_async(
                self._sub_device_key, self._hub_id, self._device_id
            )
        self._state = False

    @property
    def is_on(self):
        """Return true if it is on."""
        return self._state

    @property
    def rgb_color(self):
        """Return the rgb_color color value."""
        return self._rgb_color

    @property
    def brightness(self):
        """Return the brightness value."""
        return self._brightness

    @property
    def color_temp(self):
        """Return the color_temp value."""
        return self._color_temp

    @property
    def max_mireds(self):
        """Return the max_mireds value."""
        return self._max_mireds

    @property
    def min_mireds(self):
        """Return the min_mireds value."""
        return self._min_mireds

    @property
    def color_mode(self):
        """Return the color mode of the light."""
        return self._color_mode

    @property
    def supported_color_modes(self):
        """Return the color mode of the light."""
        return self._supported_color_modes

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""

        return self._attributes

    @property
    def unique_id(self):
        """A unique identifier for this entity."""
        return self._entity_id


class LifeSmartLight(LightEntity):
    """Representation of a LifeSmartLight."""

    def __init__(
        self, device, raw_device_data, sub_device_key, sub_device_data, client
    ) -> None:
        """Initialize the light."""

        device_name = raw_device_data.get(DEVICE_NAME_KEY, "")
        device_type = raw_device_data[DEVICE_TYPE_KEY]
        hub_id = raw_device_data[HUB_ID_KEY]
        device_id = raw_device_data[DEVICE_ID_KEY]

        self._attr_has_entity_name = True
        self.light_name = device_name
        self.device_id = device_id
        self.hub_id = hub_id
        self.sub_device_key = sub_device_key
        self.device_type = device_type
        self.raw_device_data = raw_device_data
        self._device = device
        self._client = client
        self.entity_id = generate_entity_id(
            device_type, hub_id, device_id, sub_device_key
        )

        self._brightness = None
        self._color_temp = None
        self._effect = None
        self._effect_list = None
        self._dyn_data = raw_device_data.get(DEVICE_DATA_KEY, {}).get("DYN")
        if device_type in QUANTUM_TYPES:
            self._dyn_data = raw_device_data.get(DEVICE_DATA_KEY, {}).get("P3")
        _LOGGER.info("Light: %s added", str(self.entity_id))
        _LOGGER.info("Light: sub_device_key: %s ", str(sub_device_key))
        _LOGGER.info("Light: sub_device_data: %s ", str(sub_device_data))

        if device_type in QUANTUM_TYPES:
            self._state = _is_on_type(sub_device_data.get("type"))
            self._color_mode = ColorMode.RGBW
            self._supported_color_modes = {ColorMode.RGBW}
            self._max_mireds = None
            self._min_mireds = None
            brightness = raw_device_data.get(DEVICE_DATA_KEY, {}).get("P1", {}).get(
                "val"
            )
            if brightness is not None:
                self._brightness = round(max(0, min(100, brightness)) * 255 / 100)
            if self._dyn_data is not None and _is_on_type(self._dyn_data.get("type")):
                self._effect = _effect_from_dyn_value(self._dyn_data.get("val"))

            value = sub_device_data["val"]
            rgbhexstr = f"{value:x}"
            rgbhexstr = rgbhexstr.zfill(8)
            rgbhex = bytes.fromhex(rgbhexstr)
            rgbhex = struct.unpack("BBBB", rgbhex)
            self._rgbw_color = rgbhex[1:] + (rgbhex[0],)
        elif device_type in LIGHT_DIMMER_TYPES:
            self._color_mode = ColorMode.COLOR_TEMP
            self._supported_color_modes = {ColorMode.COLOR_TEMP}
            self._max_mireds = MAX_MIREDS
            self._min_mireds = MIN_MIREDS
            for data_idx in sub_device_data:
                if data_idx == "P1":
                    # set on/off
                    if _is_on_type(sub_device_data[data_idx].get("type")):
                        self._state = True
                    else:
                        self._state = False
                    # set brightness
                    self._brightness = sub_device_data[data_idx]["val"]
                elif data_idx == "P2":
                    # set color temp
                    ratio = 1 - (sub_device_data[data_idx]["val"] / 255)
                    self._color_temp = (
                        int((self._max_mireds - self._min_mireds) * ratio)
                        + self._min_mireds
                    )
        else:
            self._state = _is_on_type(sub_device_data.get("type"))

            if sub_device_key == "P1":
                self._color_mode = ColorMode.COLOR_TEMP
                self._supported_color_modes = {ColorMode.COLOR_TEMP}
            elif sub_device_key in ["HS"]:
                self._color_mode = ColorMode.HS
                self._supported_color_modes = {ColorMode.HS}
            elif sub_device_key in ["RGBW", "RGB"]:
                self._color_mode = ColorMode.RGBW
                self._supported_color_modes = {ColorMode.RGBW}
                if self._dyn_data is not None:
                    self._effect_list = list(DYN_EFFECTS)
                    if _is_on_type(self._dyn_data.get("type")):
                        self._effect = _effect_from_dyn_value(
                            self._dyn_data.get("val")
                        )
            else:
                self._color_mode = ColorMode.ONOFF
                self._supported_color_modes = {ColorMode.ONOFF}

            value = sub_device_data["val"]
            if sub_device_key in ["HS"]:
                if value == 0:
                    self._hs = None
                else:
                    rgbhexstr = f"{value:x}"
                    rgbhexstr = rgbhexstr.zfill(8)
                    rgbhex = bytes.fromhex(rgbhexstr)
                    rgba = struct.unpack("BBBB", rgbhex)
                    rgb = rgba[1:]
                    self._hs = color_util.color_RGB_to_hs(*rgb)
                    _LOGGER.debug("hs: %s", str(self._hs))
            elif sub_device_key in ["RGB_0"]:
                if value == 0:
                    self._rgb_color = None
                else:
                    rgbhexstr = f"{value:x}"
                    rgbhexstr = rgbhexstr.zfill(8)
                    rgbhex = bytes.fromhex(rgbhexstr)
                    rgba = struct.unpack("BBBB", rgbhex)
                    self._rgb_color = rgba[1:]
                    _LOGGER.debug("rgb: %s", str(self._rgb_color))
            elif sub_device_key in ["RGBW", "RGB"]:
                rgbhexstr = f"{value:x}"
                rgbhexstr = rgbhexstr.zfill(8)
                rgbhex = bytes.fromhex(rgbhexstr)
                rgbhex = struct.unpack("BBBB", rgbhex)
                # convert from wrgb to rgbw tuple
                self._rgbw_color = rgbhex[1:] + (rgbhex[0],)
                _LOGGER.debug("rgbw: %s", str(self._rgbw_color))

        super().__init__()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.hub_id, self.device_id)},
            name=self.light_name,
            manufacturer=MANUFACTURER,
            model=self.device_type,
            sw_version=self.raw_device_data.get(DEVICE_VERSION_KEY),
            via_device=(DOMAIN, self.hub_id),
        )

    async def async_added_to_hass(self):
        """Add to Hass."""
        if self.device_type not in SPOT_TYPES:
            return
        rmdata = {}
        rmlist = await self._client.get_ir_remote_list_async(self.hub_id)
        for device_id in rmlist:
            if device_id != self.device_id:
                continue

            rms = await self._client.get_ir_remote_async(self.hub_id, device_id)
            rms["category"] = rmlist[device_id]["category"]
            rms["brand"] = rmlist[device_id]["brand"]
            rmdata[device_id] = rms
        _LOGGER.debug("Remote List: %s", str(rmdata))
        # self.attribution ["remotelist"] = rmdata

    @property
    def is_on(self):
        """Return true if it is on."""
        return self._state

    @property
    def hs_color(self):
        """Return the hs color value."""
        return self._hs

    @property
    def rgbw_color(self):
        """Return the rgbw_color color value."""
        return self._rgbw_color

    @property
    def rgb_color(self):
        """Return the rgb_color color value."""
        return self._rgb_color

    @property
    def brightness(self):
        """Return the brightness value."""
        return self._brightness

    @property
    def color_temp(self):
        """Return the color_temp value."""
        return self._color_temp

    @property
    def max_mireds(self):
        """Return the max_mireds value."""
        return self._max_mireds

    @property
    def min_mireds(self):
        """Return the min_mireds value."""
        return self._min_mireds

    # @property
    # def supported_features(self):
    #    """Return the supported features."""
    #    return SUPPORT_COLOR + SUPPORT_BRIGHTNESS

    @property
    def color_mode(self):
        """Return the color mode of the light."""
        return self._color_mode

    @property
    def supported_color_modes(self):
        """Return the color mode of the light."""
        return self._supported_color_modes

    @property
    def effect(self):
        """Return the current light effect."""
        return self._effect

    @property
    def effect_list(self):
        """Return supported light effects."""
        return self._effect_list

    async def async_turn_on(self, **kwargs):
        """Turn the light on."""
        if self.device_type in QUANTUM_TYPES:
            if ATTR_BRIGHTNESS in kwargs:
                brightness = round(max(0, min(255, kwargs[ATTR_BRIGHTNESS])) * 100 / 255)
                if (
                    await self._client.send_epset_async(
                        "0xcf",
                        brightness,
                        "P1",
                        self.hub_id,
                        self.device_id,
                    )
                    == 0
                ):
                    self._brightness = kwargs[ATTR_BRIGHTNESS]
                    self._state = True
                    self.async_schedule_update_ha_state()
            if ATTR_RGBW_COLOR in kwargs:
                self._rgbw_color = kwargs[ATTR_RGBW_COLOR]
                rgbhex = (self._rgbw_color[-1],) + self._rgbw_color[:-1]
                rgbhex = binascii.hexlify(struct.pack("BBBB", *rgbhex)).decode(
                    "ASCII"
                )
                rgbhex = int(rgbhex, 16)
                if (
                    await self._client.send_epset_async(
                        "0xff",
                        rgbhex,
                        "P2",
                        self.hub_id,
                        self.device_id,
                    )
                    == 0
                ):
                    self._state = True
                    self.async_schedule_update_ha_state()
            if ATTR_BRIGHTNESS not in kwargs and ATTR_RGBW_COLOR not in kwargs:
                if (
                    await self._client.turn_on_light_swith_async(
                        "P1", self.hub_id, self.device_id
                    )
                    == 0
                ):
                    self._state = True
                    self.async_schedule_update_ha_state()
        elif self.device_type in LIGHT_DIMMER_TYPES:
            if ATTR_BRIGHTNESS in kwargs:
                if (
                    await super().async_lifesmart_epset(
                        "0xcf", kwargs[ATTR_BRIGHTNESS], "P1"
                    )
                    == 0
                ):
                    self._brightness = kwargs[ATTR_BRIGHTNESS]
                    self.async_schedule_update_ha_state()
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                ratio = (kwargs[ATTR_COLOR_TEMP_KELVIN] - self._min_mireds) / (
                    self._max_mireds - self._min_mireds
                )
                val = int((-ratio + 1) * 255)
                if await super().async_lifesmart_epset("0xcf", val, "P2") == 0:
                    self._color_temp = kwargs[ATTR_COLOR_TEMP_KELVIN]
                    self.async_schedule_update_ha_state()
            if await super().async_lifesmart_epset("0x81", 1, "P1") == 0:
                self._state = True
                self.async_schedule_update_ha_state()

        else:
            if self.color_mode == ColorMode.HS:
                if ATTR_HS_COLOR in kwargs:
                    self._hs = kwargs[ATTR_HS_COLOR]

                rgb = color_util.color_hs_to_RGB(*self._hs)
                rgba = (0, *rgb)
                rgbhex = binascii.hexlify(struct.pack("BBBB", *rgba)).decode("ASCII")
                rgbhex = int(rgbhex, 16)

                if await super().async_lifesmart_epset("0xff", rgbhex, self._idx) == 0:
                    self._state = True
                    self.async_schedule_update_ha_state()

            if self.color_mode == ColorMode.RGB:
                if ATTR_RGB_COLOR in kwargs:
                    self._rgb_color = kwargs[ATTR_RGB_COLOR]
                # convert rgb to wrgb tuple
                rgbhex = (0, *self._rgb_color)
                rgbhex = binascii.hexlify(struct.pack("BBBB", *rgbhex)).decode("ASCII")
                rgbhex = int(rgbhex, 16)

                if await super().async_lifesmart_epset("0xff", rgbhex, self._idx) == 0:
                    self._state = True
                    self.async_schedule_update_ha_state()

            if self.color_mode == ColorMode.RGBW:
                if ATTR_EFFECT in kwargs and self._dyn_data is not None:
                    dyn_value = _dyn_value_from_effect(kwargs[ATTR_EFFECT])
                    if dyn_value is None:
                        _LOGGER.warning("Unsupported DYN effect: %s", kwargs[ATTR_EFFECT])
                        return

                    if not self._state:
                        await self._client.turn_on_light_swith_async(
                            self.sub_device_key, self.hub_id, self.device_id
                        )

                    if (
                        await self._client.send_epset_async(
                            "0xff",
                            dyn_value,
                            "DYN",
                            self.hub_id,
                            self.device_id,
                        )
                        == 0
                    ):
                        self._effect = _effect_from_dyn_value(dyn_value)
                        self._state = True
                        self.async_schedule_update_ha_state()
                elif ATTR_RGBW_COLOR in kwargs:
                    self._rgbw_color = kwargs[ATTR_RGBW_COLOR]
                    # convert rgbw to wrgb tuple
                    rgbhex = (self._rgbw_color[-1],) + self._rgbw_color[:-1]
                    rgbhex = binascii.hexlify(struct.pack("BBBB", *rgbhex)).decode(
                        "ASCII"
                    )
                    rgbhex = int(rgbhex, 16)

                    if self._dyn_data is not None:
                        await self._client.turn_off_light_swith_async(
                            "DYN", self.hub_id, self.device_id
                        )
                        self._effect = None

                    if (
                        await self._client.send_epset_async(
                            "0xff",
                            rgbhex,
                            self.sub_device_key,
                            self.hub_id,
                            self.device_id,
                        )
                        == 0
                    ):
                        self._state = True
                        self.async_schedule_update_ha_state()
                elif (
                    await self._client.turn_on_light_swith_async(
                        self.sub_device_key, self.hub_id, self.device_id
                    )
                    == 0
                ):
                    self._state = True
                    self.async_schedule_update_ha_state()

            if self.color_mode == ColorMode.ONOFF and (
                await self._client.turn_on_light_swith_async(
                    self.sub_device_key, self.hub_id, self.device_id
                )
                == 0
            ):
                self._state = True
                self.async_schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the light off."""
        if self.device_type in QUANTUM_TYPES:
            if (
                await self._client.turn_off_light_swith_async(
                    "P1", self.hub_id, self.device_id
                )
                == 0
            ):
                self._state = False
                self.async_schedule_update_ha_state()

        elif self.device_type in LIGHT_DIMMER_TYPES:
            if await super().async_lifesmart_epset("0x80", 0, "P1") == 0:
                self._state = False
                self.async_schedule_update_ha_state()

        elif self.device_type in SPOT_TYPES:
            if ATTR_RGBW_COLOR in kwargs:
                self._rgbw_color = kwargs[ATTR_RGBW_COLOR]
                # convert rgbw to wrgb tuple
                rgbhex = (self._rgbw_color[-1],) + self._rgbw_color[:-1]
                rgbhex = binascii.hexlify(struct.pack("BBBB", *rgbhex)).decode("ASCII")
                rgbhex = int(rgbhex, 16)

                if (
                    await self._client.send_epset_async(
                        "0xfe",
                        rgbhex,
                        self.sub_device_key,
                        self.hub_id,
                        self.device_id,
                    )
                    == 0
                ):
                    self._state = False
                    self.async_schedule_update_ha_state()
            elif (
                await self._client.turn_off_light_swith_async(
                    self.sub_device_key, self.hub_id, self.device_id
                )
                == 0
            ):
                self._state = False
                self.async_schedule_update_ha_state()

        elif (
            await self._client.turn_off_light_swith_async(
                self.sub_device_key, self.hub_id, self.device_id
            )
            == 0
        ):
            self._state = False
            self.async_schedule_update_ha_state()

    @property
    def unique_id(self):
        """A unique identifier for this entity."""
        return self.entity_id
