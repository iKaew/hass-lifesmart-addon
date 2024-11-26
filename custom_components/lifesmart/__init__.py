"""lifesmart by @ikaew."""
import asyncio
import datetime
import json
import logging
import sys
import threading
import time

import websocket

from homeassistant.components import climate
from homeassistant.components.climate import FAN_HIGH, FAN_LOW, FAN_MEDIUM
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_MAX_MIREDS,
    ATTR_MIN_MIREDS,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_REGION, STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.entity import Entity

from .const import (
    BINARY_SENSOR_TYPES,
    CLIMATE_TYPES,
    CONF_AI_INCLUDE_AGTS,
    CONF_AI_INCLUDE_ITEMS,
    CONF_EXCLUDE_AGTS,
    CONF_EXCLUDE_ITEMS,
    CONF_LIFESMART_APPKEY,
    CONF_LIFESMART_APPTOKEN,
    CONF_LIFESMART_USERID,
    CONF_LIFESMART_USERPASSWORD,
    COVER_TYPES,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DIGITAL_DOORLOCK_ALARM_EVENT_KEY,
    DIGITAL_DOORLOCK_BATTERY_EVENT_KEY,
    DIGITAL_DOORLOCK_LOCK_EVENT_KEY,
    DOMAIN,
    EV_SENSOR_TYPES,
    GAS_SENSOR_TYPES,
    HUB_ID_KEY,
    LIFESMART_HVAC_STATE_LIST,
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    LIFESMART_STATE_MANAGER,
    LIGHT_DIMMER_TYPES,
    LIGHT_SWITCH_TYPES,
    LOCK_TYPES,
    OT_SENSOR_TYPES,
    SMART_PLUG_TYPES,
    SPOT_TYPES,
    SUBDEVICE_INDEX_KEY,
    SUPPORTED_PLATFORMS,
    SUPPORTED_SUB_BINARY_SENSORS,
    SUPPORTED_SUB_SWITCH_TYPES,
    SUPPORTED_SWTICH_TYPES,
    UPDATE_LISTENER,
)
from .lifesmart_client import LifeSmartClient

sys.setrecursionlimit(100000)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Initialize a setup of the lifesamrt addon."""
    hass.data.setdefault(DOMAIN, {})

    app_key = config_entry.data.get(CONF_LIFESMART_APPKEY)
    app_token = config_entry.data.get(CONF_LIFESMART_APPTOKEN)
    user_id = config_entry.data.get(CONF_LIFESMART_USERID)
    user_password = config_entry.data.get(CONF_LIFESMART_USERPASSWORD)
    region = config_entry.data.get(CONF_REGION)
    exclude_devices = config_entry.data.get(CONF_EXCLUDE_ITEMS)
    exclude_hubs = config_entry.data.get(CONF_EXCLUDE_AGTS)
    ai_include_hubs = config_entry.data.get(CONF_AI_INCLUDE_AGTS)
    ai_include_items = config_entry.data.get(CONF_AI_INCLUDE_ITEMS)

    # default data
    if exclude_devices is None:
        exclude_devices = []
    if exclude_hubs is None:
        exclude_hubs = []
    if ai_include_hubs is None:
        ai_include_hubs = []
    if ai_include_items is None:
        ai_include_items = []

    # Update listener for config option changes
    update_listener = config_entry.add_update_listener(_async_update_listener)

    lifesmart_client = LifeSmartClient(
        region,
        app_key,
        app_token,
        user_id,
        user_password,
    )

    await lifesmart_client.login_async()

    devices = await lifesmart_client.get_all_device_async()

    _LOGGER.info(devices)

    hass.data[DOMAIN][config_entry.entry_id] = {
        "client": lifesmart_client,
        "exclude_devices": exclude_devices,
        "exclude_hubs": exclude_hubs,
        "ai_include_hubs": ai_include_hubs,
        "ai_include_items": ai_include_items,
        "devices": devices,
        UPDATE_LISTENER: update_listener,
    }

    for platform in SUPPORTED_PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(config_entry, platform)       

    async def data_update_handler(msg):
        data = msg["msg"]
        device_type = data[DEVICE_TYPE_KEY]
        hub_id = data[HUB_ID_KEY]
        device_id = data[DEVICE_ID_KEY]
        sub_device_key = data[SUBDEVICE_INDEX_KEY]

        if (
            sub_device_key != "s"
            and device_id not in exclude_devices
            and hub_id not in exclude_hubs
        ):
            entity_id = generate_entity_id(
                device_type, hub_id, device_id, sub_device_key
            )

            if (  # noqa: SIM114
                device_type in SUPPORTED_SWTICH_TYPES
                and sub_device_key in SUPPORTED_SUB_SWITCH_TYPES
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif (
                device_type in BINARY_SENSOR_TYPES
                and sub_device_key in SUPPORTED_SUB_BINARY_SENSORS
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )

            elif device_type in COVER_TYPES and sub_device_key == "P1":
                attrs = dict(hass.states.get(entity_id).attributes)
                nval = data["val"]
                ntype = data["type"]
                attrs["current_position"] = nval & 0x7F
                # _LOGGER.debug("websocket_cover_attrs: %s",str(attrs))
                nstat = None
                if ntype % 2 == 0:
                    if nval > 0:
                        nstat = "open"
                    else:
                        nstat = "closed"
                elif nval & 0x80 == 0x80:
                    nstat = "opening"
                else:
                    nstat = "closing"
                hass.states.set(entity_id, nstat, attrs)
            elif device_type in EV_SENSOR_TYPES:
                attrs = hass.states.get(entity_id).attributes
                hass.states.set(entity_id, data["v"], attrs)
            elif device_type in GAS_SENSOR_TYPES and data["val"] > 0:
                attrs = hass.states.get(entity_id).attributes
                hass.states.set(entity_id, data["val"], attrs)
            elif device_type in SPOT_TYPES or device_type in LIGHT_SWITCH_TYPES:
                # attrs = dict(hass.states.get(entity_id).attributes)
                _LOGGER.debug("websocket_light_msg: %s ", str(msg))
                # _LOGGER.debug("websocket_light_attrs: %s", str(attrs))
                value = data["val"]
                idx = sub_device_key

                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
                """
                if idx in ["HS"]:
                    if value == 0:
                        attrs[ATTR_HS_COLOR] = None
                    else:
                        rgbhexstr = "%x" % value
                        rgbhexstr = rgbhexstr.zfill(8)
                        rgbhex = bytes.fromhex(rgbhexstr)
                        rgba = struct.unpack("BBBB", rgbhex)
                        rgb = rgba[1:]
                        attrs[ATTR_HS_COLOR] = color_util.color_RGB_to_hs(*rgb)
                        _LOGGER.info("HS: %s", str(attrs[ATTR_HS_COLOR]))
                elif idx in ["RGB_O"]:
                    if value == 0:
                        attrs[ATTR_RGB_COLOR] = None
                    else:
                        rgbhexstr = "%x" % value
                        rgbhexstr = rgbhexstr.zfill(8)
                        rgbhex = bytes.fromhex(rgbhexstr)
                        rgba = struct.unpack("BBBB", rgbhex)
                        rgb = rgba[1:]
                        attrs[ATTR_RGB_COLOR] = rgb
                        _LOGGER.info("RGB: %s", str(attrs[ATTR_RGB_COLOR]))
                elif idx in ["RGBW", "RGB"]:
                    rgbhexstr = "%x" % value
                    rgbhexstr = rgbhexstr.zfill(8)
                    rgbhex = bytes.fromhex(rgbhexstr)
                    rgbhex = struct.unpack("BBBB", rgbhex)
                    # convert from wrgb to rgbw tuple
                    attrs[ATTR_RGBW_COLOR] = rgbhex[1:] + (rgbhex[0],)
                    _LOGGER.info("RGBW: %s", str(attrs[ATTR_RGBW_COLOR]))
                """

            elif device_type in LIGHT_DIMMER_TYPES:
                attrs = dict(hass.states.get(entity_id).attributes)
                state = hass.states.get(entity_id).state
                _LOGGER.debug("websocket_light_msg: %s ", str(msg))
                _LOGGER.debug("websocket_light_attrs: %s", str(attrs))
                value = data["val"]
                idx = sub_device_key
                if idx in ["P1"]:
                    if data["type"] % 2 == 1:
                        attrs[ATTR_BRIGHTNESS] = value
                        hass.states.set(entity_id, STATE_ON, attrs)
                    else:
                        hass.states.set(entity_id, STATE_OFF, attrs)
                elif idx in ["P2"]:
                    ratio = 1 - (value / 255)
                    attrs[ATTR_COLOR_TEMP] = (
                        int((attrs[ATTR_MAX_MIREDS] - attrs[ATTR_MIN_MIREDS]) * ratio)
                        + attrs[ATTR_MIN_MIREDS]
                    )
                    hass.states.set(entity_id, state, attrs)

            elif device_type in CLIMATE_TYPES:
                _idx = sub_device_key
                attrs = dict(hass.states.get(entity_id).attributes)
                nstat = hass.states.get(entity_id).state
                if _idx == "O":
                    if data["type"] % 2 == 1:
                        nstat = attrs["last_mode"]
                        hass.states.set(entity_id, nstat, attrs)
                    else:
                        nstat = climate.const.HVACMode.OFF
                        hass.states.set(entity_id, nstat, attrs)
                if _idx == "P1":
                    if data["type"] % 2 == 1:
                        nstat = climate.const.HVACMode.HEAT
                        hass.states.set(entity_id, nstat, attrs)
                    else:
                        nstat = climate.const.HVACMode.OFF
                        hass.states.set(entity_id, nstat, attrs)
                if _idx == "P2":
                    if data["type"] % 2 == 1:
                        attrs["Heating"] = "true"
                        hass.states.set(entity_id, nstat, attrs)
                    else:
                        attrs["Heating"] = "false"
                        hass.states.set(entity_id, nstat, attrs)
                elif _idx == "MODE":
                    if data["type"] == 206:
                        if nstat != climate.const.HVACMode.OFF:
                            nstat = LIFESMART_HVAC_STATE_LIST[data["val"]]
                        attrs["last_mode"] = nstat
                        hass.states.set(entity_id, nstat, attrs)
                elif _idx == "F":
                    if data["type"] == 206:
                        attrs["fan_mode"] = get_fan_mode(data["val"])
                        hass.states.set(entity_id, nstat, attrs)
                elif _idx == "tT" or _idx == "P3":  # noqa: PLR1714
                    if data["type"] == 136:
                        attrs["temperature"] = data["v"]
                        hass.states.set(entity_id, nstat, attrs)
                elif _idx == "T" or _idx == "P4":  # noqa: PLR1714
                    if data["type"] == 8 or data["type"] == 9:
                        attrs["current_temperature"] = data["v"]
                        hass.states.set(entity_id, nstat, attrs)
            elif device_type in LOCK_TYPES:
                if sub_device_key in [
                    DIGITAL_DOORLOCK_BATTERY_EVENT_KEY,
                    DIGITAL_DOORLOCK_ALARM_EVENT_KEY,
                    DIGITAL_DOORLOCK_LOCK_EVENT_KEY,
                ]:
                    dispatcher_send(
                        hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                    )
            elif device_type in OT_SENSOR_TYPES and sub_device_key in [
                "Z",
                "V",
                "P3",
                "P4",
            ]:
                attrs = hass.states.get(entity_id).attributes
                hass.states.set(entity_id, data["v"], attrs)
            elif device_type in SMART_PLUG_TYPES:
                if sub_device_key == "P1":
                    attrs = hass.states.get(entity_id).attributes
                    if data["type"] % 2 == 1:
                        hass.states.set(entity_id, STATE_ON, attrs)
                    else:
                        hass.states.set(entity_id, STATE_OFF, attrs)
                elif sub_device_key in ["P2", "P3"]:
                    attrs = hass.states.get(entity_id).attributes
                    hass.states.set(entity_id, data["v"], attrs)
            else:
                _LOGGER.debug("Event is not supported")

        # AI event
        if (
            sub_device_key == "s"
            and device_id in ai_include_items
            and data[HUB_ID_KEY] in ai_include_hubs
        ):
            _LOGGER.info("AI Event: %s", str(msg))
            device_type = data["devtype"]
            hub_id = data[HUB_ID_KEY]
            entity_id = (
                "switch."
                + (
                    device_type + "_" + hub_id + "_" + device_id + "_" + sub_device_key
                ).lower()
            )
            """
            attrs = hass.states.get(entity_id).attributes

            if data["stat"] == 3:
                hass.states.set(entity_id, STATE_ON, attrs)
            elif data["stat"] == 4:
                hass.states.set(entity_id, STATE_OFF, attrs)
            """

    def on_message(ws, message):
        _LOGGER.debug("websocket_msg: %s", str(message))
        msg = json.loads(message)
        if "type" not in msg:
            return
        if msg["type"] != "io":
            return
        asyncio.run(data_update_handler(msg))

    def on_error(ws, error):
        _LOGGER.error("Websocket_error: %s", str(error))

    def on_close(ws, close_status_code, close_msg):
        _LOGGER.debug(
            "lifesmart websocket closed...: %s %s",
            str(close_status_code),
            str(close_msg),
        )

    def on_open(ws):
        client = hass.data[DOMAIN][config_entry.entry_id]["client"]
        send_data = client.generate_wss_auth()
        ws.send(send_data)
        _LOGGER.debug("LifeSmart websocket sending_data")

    async def send_keys(call):
        """Handle the service call."""
        agt = call.data[HUB_ID_KEY]
        me = call.data[DEVICE_ID_KEY]
        ai = call.data["ai"]
        category = call.data["category"]
        brand = call.data["brand"]
        keys = call.data["keys"]
        restkey = await hass.data[DOMAIN][config_entry.entry_id][
            "client"
        ].send_ir_key_async(
            agt,
            ai,
            me,
            category,
            brand,
            keys,
        )
        _LOGGER.debug("sendkey: %s", str(restkey))

    async def send_ackeys(call):
        """Handle the service call."""
        agt = call.data[HUB_ID_KEY]
        me = call.data[DEVICE_ID_KEY]
        ai = call.data["ai"]
        category = call.data["category"]
        brand = call.data["brand"]
        keys = call.data["keys"]
        power = call.data["power"]
        mode = call.data["mode"]
        temp = call.data["temp"]
        wind = call.data["wind"]
        swing = call.data["swing"]
        restackey = await hass.data[DOMAIN][config_entry.entry_id][
            "client"
        ].send_ir_ackey_async(
            agt,
            ai,
            me,
            category,
            brand,
            keys,
            power,
            mode,
            temp,
            wind,
            swing,
        )
        _LOGGER.debug("sendkey: %s", str(restackey))

    async def scene_set_async(call):
        """Handle the service call."""
        agt = call.data[HUB_ID_KEY]
        id = call.data["id"]
        restkey = await hass.data[DOMAIN][config_entry.entry_id][
            "client"
        ].set_scene_async(
            agt,
            id,
        )
        _LOGGER.debug("scene_set: %s", str(restkey))

    hass.services.async_register(DOMAIN, "send_keys", send_keys)
    hass.services.async_register(DOMAIN, "send_ackeys", send_ackeys)
    hass.services.async_register(DOMAIN, "scene_set", scene_set_async)

    ws = websocket.WebSocketApp(
        lifesmart_client.get_wss_url(),
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.on_open = on_open
    hass.data[DOMAIN][LIFESMART_STATE_MANAGER] = LifeSmartStatesManager(ws=ws)
    hass.data[DOMAIN][LIFESMART_STATE_MANAGER].start_keep_alive()
    return True


async def _async_update_listener(hass, config_entry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class LifeSmartDevice(Entity):
    """LifeSmart base device."""

    def __init__(self, dev, lifesmart_client) -> None:
        """Initialize the switch."""

        self._name = dev[DEVICE_NAME_KEY]
        self._device_name = dev[DEVICE_NAME_KEY]
        self._agt = dev[HUB_ID_KEY]
        self._me = dev[DEVICE_ID_KEY]
        self._devtype = dev["devtype"]
        self._client = lifesmart_client
        attrs = {
            HUB_ID_KEY: self._agt,
            DEVICE_ID_KEY: self._me,
            "devtype": self._devtype,
        }
        self._attributes = attrs

    @property
    def object_id(self):
        """Return LifeSmart device id."""
        return self.entity_id

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def name(self):
        """Return LifeSmart device name."""
        return self._name

    @property
    def assumed_state(self):
        """Return true if we do optimistic updates."""
        return False

    @property
    def should_poll(self):
        """Check with the entity for an updated state."""
        return False

    async def async_lifesmart_epset(self, type, val, idx):
        """Send command to lifesmart device."""
        agt = self._agt
        me = self._me
        responsecode = await self._client.send_epset_async(type, val, idx, agt, me)
        return responsecode

    async def async_lifesmart_epget(self):
        """Get lifesmart device info."""
        agt = self._agt
        me = self._me
        response = await self._client.get_epget_async(agt, me)
        return response

    async def async_lifesmart_sceneset(self, type, rgbw):
        """Set the scene."""
        agt = self._agt
        id = self._me
        response = self._client.set_scene_async(agt, id)
        return response["code"]


class LifeSmartStatesManager(threading.Thread):
    """Instance to manage websocket to get push data from LifeSmart service."""

    def __init__(self, ws) -> None:
        """Init LifeSmart Update Manager."""
        threading.Thread.__init__(self)
        self._run = False
        self._lock = threading.Lock()
        self._ws = ws

    def run(self):  # noqa: D102
        while self._run:
            _LOGGER.debug("lifesmart: starting wss")
            self._ws.run_forever()
            _LOGGER.debug("lifesmart: restart wss")
            time.sleep(10)

    def start_keep_alive(self):
        """Start keep alive mechanism."""
        with self._lock:
            self._run = True
            threading.Thread.start(self)

    def stop_keep_alive(self):
        """Stop keep alive mechanism."""
        with self._lock:
            self._run = False
            self.join()


def get_fan_mode(_fanspeed):
    """Convert fan speed to fan mode."""
    fanmode = None
    if _fanspeed < 30:
        fanmode = FAN_LOW
    elif _fanspeed < 65 and _fanspeed >= 30:
        fanmode = FAN_MEDIUM
    elif _fanspeed >= 65:
        fanmode = FAN_HIGH
    return fanmode


def get_platform_by_device(device_type, sub_device=None):
    """Convert lifesmart device subtype tp HA device type."""
    if device_type in SUPPORTED_SWTICH_TYPES:
        return Platform.SWITCH
    elif device_type in BINARY_SENSOR_TYPES:
        return Platform.BINARY_SENSOR
    elif device_type in COVER_TYPES:
        return Platform.COVER
    elif device_type in EV_SENSOR_TYPES + GAS_SENSOR_TYPES + OT_SENSOR_TYPES:
        return Platform.SENSOR
    elif device_type in SPOT_TYPES + LIGHT_SWITCH_TYPES + LIGHT_DIMMER_TYPES:
        return Platform.LIGHT
    elif device_type in CLIMATE_TYPES:
        return Platform.CLIMATE
    elif device_type in LOCK_TYPES and sub_device == DIGITAL_DOORLOCK_BATTERY_EVENT_KEY:
        return Platform.SENSOR
    elif (
        device_type in LOCK_TYPES
        and sub_device == DIGITAL_DOORLOCK_LOCK_EVENT_KEY
        or device_type in LOCK_TYPES
        and sub_device == DIGITAL_DOORLOCK_ALARM_EVENT_KEY
    ):
        return Platform.BINARY_SENSOR
    elif device_type in SMART_PLUG_TYPES and sub_device == "P1":
        return Platform.SWITCH
    elif device_type in SMART_PLUG_TYPES and sub_device in ["P2", "P3"]:
        return Platform.SENSOR
    return ""


def generate_entity_id(device_type, hub_id, device_id, idx=None):
    """Generate unique id for entity in HA."""
    hub_id = hub_id.replace("__", "_").replace("-", "_")
    if idx:
        sub_device = idx
    else:
        sub_device = None

    if device_type in [
        *SUPPORTED_SWTICH_TYPES,
        *BINARY_SENSOR_TYPES,
        *EV_SENSOR_TYPES,
        *GAS_SENSOR_TYPES,
        *SPOT_TYPES,
        *LIGHT_SWITCH_TYPES,
        *OT_SENSOR_TYPES,
        *SMART_PLUG_TYPES,
        *LOCK_TYPES,
    ]:
        if sub_device:
            return (
                get_platform_by_device(device_type, sub_device)
                + (
                    "."
                    + device_type
                    + "_"
                    + hub_id
                    + "_"
                    + device_id
                    + "_"
                    + sub_device
                ).lower()
            )
        else:
            return (
                # no sub device (idx)
                get_platform_by_device(device_type)
                + ("." + device_type + "_" + hub_id + "_" + device_id).lower()
            )

    elif device_type in COVER_TYPES:
        return (
            Platform.COVER
            + ("." + device_type + "_" + hub_id + "_" + device_id).lower()
        )
    elif device_type in LIGHT_DIMMER_TYPES:
        return (
            Platform.LIGHT
            + ("." + device_type + "_" + hub_id + "_" + device_id + "_P1P2").lower()
        )
    elif device_type in CLIMATE_TYPES:
        return Platform.CLIMATE + (
            "." + device_type + "_" + hub_id + "_" + device_id
        ).lower().replace(":", "_").replace("@", "_")
