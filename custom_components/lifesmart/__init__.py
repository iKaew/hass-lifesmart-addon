"""lifesmart by @ikaew."""

import asyncio
from ipaddress import ip_address
import json
import logging
import re
import sys
import threading

import voluptuous as vol
import websocket
from homeassistant.components.climate import FAN_HIGH, FAN_LOW, FAN_MEDIUM
from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_REGION, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    AIR_PURIFIER_TYPES,
    BINARY_SENSOR_TYPES,
    CLIMATE_TYPES,
    CO2_SENSOR_TYPES,
    CONF_AI_INCLUDE_AGTS,
    CONF_AI_INCLUDE_ITEMS,
    CONF_CONNECTION_TYPE,
    CONF_EXCLUDE_AGTS,
    CONF_EXCLUDE_ITEMS,
    CONF_LIFESMART_APPKEY,
    CONF_LIFESMART_APPTOKEN,
    CONF_LIFESMART_USERID,
    CONF_LIFESMART_USERPASSWORD,
    CONF_LOCAL_PASSWORD,
    CONNECTION_TYPE_CLOUD,
    CONNECTION_TYPE_LOCAL,
    COVER_TYPES,
    DEFED_DOOR_SENSOR_TYPES,
    DEFED_KEYFOB_TYPES,
    DEFED_MOTION_SENSOR_TYPES,
    DEFED_SENSOR_TYPES,
    DEFED_SIREN_TYPES,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DIGITAL_DOORLOCK_ALARM_EVENT_KEY,
    DIGITAL_DOORLOCK_BATTERY_EVENT_KEY,
    DIGITAL_DOORLOCK_DOORBELL_EVENT_KEY,
    DIGITAL_DOORLOCK_HISTORY_LOCK_EVENT_KEY,
    DIGITAL_DOORLOCK_LOCK_EVENT_KEY,
    DIGITAL_DOORLOCK_OPERATION_EVENT_KEY,
    DLT_METER_TYPES,
    DOMAIN,
    ELECTRICITY_METER_TYPES,
    ENV_SENSOR_TYPES,
    EV_SENSOR_TYPES,
    GARAGE_DOOR_TYPES,
    GAS_SENSOR_TYPES,
    GENERIC_CONTROLLER_BINARY_PORTS,
    GENERIC_CONTROLLER_SWITCH_PORTS,
    GENERIC_CONTROLLER_TYPES,
    HA_CONTROLLER_SWITCH_PORTS,
    HUB_ID_KEY,
    HUB_DEVICE_REGISTRY_ID_KEY,
    LIFESMART_SIGNAL_UPDATE_ENTITY,
    LIGHT_DIMMER_TYPES,
    LIGHT_SWITCH_TYPES,
    LOCK_TYPES,
    NATURE_CLIMATE_KEY,
    NATURE_SWITCH_PORTS,
    NATURE_TYPES,
    NOISE_SENSOR_TYPES,
    MODBUS_CONTROLLER_TYPES,
    OT_SENSOR_TYPES,
    RADAR_MOTION_SENSOR_TYPES,
    SMART_PLUG_TYPES,
    SMART_PLUG_ENERGY_TYPES,
    SMART_ALARM_TYPES,
    SMART_CAMERA_STATUS_BINARY_KEYS,
    SMART_CAMERA_STATUS_EVENT_KEY,
    SMART_CAMERA_TYPES,
    SMOKE_SENSOR_TYPES,
    SPOT_IR_TYPES,
    SPOT_TYPES,
    SUBDEVICE_INDEX_KEY,
    SUPPORTED_PLATFORMS,
    SUPPORTED_SUB_BINARY_SENSORS,
    SUPPORTED_SUB_SWITCH_TYPES,
    SUPPORTED_SWTICH_TYPES,
    TVOC_CO2_SENSOR_TYPES,
    WATER_LEAK_SENSOR_TYPES,
    is_nature_thermostat,
    normalize_lifesmart_region,
)
from .lifesmart_client import LifeSmartClient
from .lifesmart_client_local import (
    DEFAULT_LOCAL_PASSWORD,
    DEFAULT_LOCAL_PORT,
    LocalLifeSmartClient,
)
from .runtime_data import LifeSmartAvailabilityMixin, LifeSmartRuntimeData

sys.setrecursionlimit(100000)

SEND_IR_CODE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): str,
        vol.Required("hub_id"): str,
        vol.Required("ir_code"): str,
    }
)
SEND_KEYS_SCHEMA = vol.Schema(
    {
        vol.Required(HUB_ID_KEY): str,
        vol.Required(DEVICE_ID_KEY): str,
        vol.Required("ai"): str,
        vol.Required("category"): str,
        vol.Required("brand"): str,
        vol.Required("keys"): vol.Any(list, str),
    }
)
SEND_AC_KEYS_SCHEMA = SEND_KEYS_SCHEMA.extend(
    {
        vol.Optional("idx", default=""): str,
        vol.Required("power"): int,
        vol.Required("mode"): int,
        vol.Required("temp"): int,
        vol.Required("wind"): int,
        vol.Required("swing"): int,
    }
)
SCENE_SET_SCHEMA = vol.Schema(
    {vol.Required(HUB_ID_KEY): str, vol.Required("id"): str}
)

_LOGGER = logging.getLogger(__name__)


def _platforms_for_client(client) -> list[Platform]:
    """Return platforms supported by the selected transport."""
    if not getattr(client, "is_local", False):
        return SUPPORTED_PLATFORMS
    return [
        platform
        for platform in SUPPORTED_PLATFORMS
        if platform not in (Platform.BUTTON, Platform.INFRARED, Platform.REMOTE)
    ]


def _runtime_for_service(hass: HomeAssistant, data: dict) -> LifeSmartRuntimeData:
    """Resolve service data to exactly one loaded LifeSmart entry."""
    hub_id = data[HUB_ID_KEY]
    device_id = data.get(DEVICE_ID_KEY)
    matches = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if not isinstance(runtime, LifeSmartRuntimeData):
            continue
        device_matches = any(
            device.get(HUB_ID_KEY) == hub_id
            and (device_id is None or device.get(DEVICE_ID_KEY) == device_id)
            for device in runtime.devices
        )
        hub_matches = device_id is None and (
            any(hub.get(HUB_ID_KEY) == hub_id for hub in runtime.hubs)
            or any(scene.get(HUB_ID_KEY) == hub_id for scene in runtime.scenes)
        )
        if device_matches or hub_matches:
            matches.append(runtime)
    if len(matches) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="service_target_not_found",
        )
    return matches[0]


async def _async_call_lifesmart_service(hass: HomeAssistant, call) -> None:
    """Handle a LifeSmart service action using its target entry."""
    runtime = _runtime_for_service(hass, call.data)
    client = runtime.client
    try:
        if call.service == "send_ir_code":
            keys = json.dumps(
                [{"param": {"data": str(call.data["ir_code"]), "type": 1}}]
            )
            response = await client.send_ir_code_async(
                call.data[HUB_ID_KEY], call.data[DEVICE_ID_KEY], keys
            )
        elif call.service == "send_keys":
            response = await client.send_ir_key_async(
                call.data[HUB_ID_KEY],
                call.data["ai"],
                call.data[DEVICE_ID_KEY],
                call.data["category"],
                call.data["brand"],
                call.data["keys"],
            )
        elif call.service == "send_ackeys":
            response = await client.send_ir_ackey_async(
                call.data[HUB_ID_KEY],
                call.data["ai"],
                call.data[DEVICE_ID_KEY],
                call.data["category"],
                call.data["brand"],
                call.data["keys"],
                call.data["idx"],
                call.data["power"],
                call.data["mode"],
                call.data["temp"],
                call.data["wind"],
                call.data["swing"],
            )
        else:
            response = await client.set_scene_async(
                call.data[HUB_ID_KEY], call.data["id"]
            )
    except Exception as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="service_action_failed",
        ) from err

    if isinstance(response, int) and response != 0:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="service_action_rejected",
        )
    if isinstance(response, dict) and response.get("code") not in (None, 0, "success"):
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="service_action_rejected",
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register integration-wide service actions."""
    schemas = {
        "send_ir_code": SEND_IR_CODE_SCHEMA,
        "send_keys": SEND_KEYS_SCHEMA,
        "send_ackeys": SEND_AC_KEYS_SCHEMA,
        "scene_set": SCENE_SET_SCHEMA,
    }
    for service, schema in schemas.items():
        hass.services.async_register(
            DOMAIN,
            service,
            _async_call_lifesmart_service,
            schema=schema,
        )
    return True


def _dispatch_doorlock_update(
    hass, device_type, hub_id, device_id, sub_device_key, entity_id, data
):
    """Dispatch digital door lock updates to all entities affected by the event."""
    dispatcher_send(hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data)

    related_sub_device = None
    if sub_device_key == DIGITAL_DOORLOCK_LOCK_EVENT_KEY:
        related_sub_device = DIGITAL_DOORLOCK_HISTORY_LOCK_EVENT_KEY
    elif sub_device_key == DIGITAL_DOORLOCK_HISTORY_LOCK_EVENT_KEY:
        related_sub_device = DIGITAL_DOORLOCK_LOCK_EVENT_KEY

    if related_sub_device is None:
        return

    related_entity_id = generate_entity_id(
        device_type, hub_id, device_id, related_sub_device
    )
    related_data = dict(data)
    related_data[SUBDEVICE_INDEX_KEY] = related_sub_device
    dispatcher_send(
        hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{related_entity_id}", related_data
    )


def _is_on_type(value) -> bool:
    """Return True when a LifeSmart type value represents on."""
    try:
        return int(str(value), 0) % 2 == 1
    except (TypeError, ValueError):
        return False


async def _async_refresh_device_availability(
    runtime_data: LifeSmartRuntimeData,
) -> None:
    """Refresh device availability after the websocket reconnects."""
    try:
        devices = await runtime_data.client.get_all_device_async()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Unable to refresh LifeSmart device availability: %s", type(err).__name__
        )
        return

    if not isinstance(devices, list):
        _LOGGER.warning("Unable to refresh LifeSmart device availability")
        return

    for device in devices:
        hub_id = device.get(HUB_ID_KEY)
        device_id = device.get(DEVICE_ID_KEY)
        status = device.get("stat")
        if hub_id is None or device_id is None or status is None:
            continue
        runtime_data.set_device_available(hub_id, device_id, status == 1)


async def _async_discover_scenes(
    client: LifeSmartClient,
    hub_ids: set[str],
    exclude_hubs: list[str],
) -> list[dict]:
    """Discover and normalize scenes without blocking normal device setup."""

    async def async_get_hub_scenes(hub_id: str) -> tuple[str, object]:
        try:
            return hub_id, await client.get_all_scene_async(hub_id)
        except Exception as err:  # Scene support is optional for existing entries.
            _LOGGER.warning(
                "Unable to retrieve LifeSmart scenes for hub %s: %s",
                hub_id,
                type(err).__name__,
            )
            return hub_id, None

    included_hubs = sorted(hub_ids - set(exclude_hubs))
    responses = await asyncio.gather(
        *(async_get_hub_scenes(hub_id) for hub_id in included_hubs)
    )
    scenes = []
    seen_scene_keys = set()
    for hub_id, response in responses:
        if response is None:
            continue
        if not isinstance(response, list):
            _LOGGER.warning(
                "LifeSmart scene discovery returned an invalid response for hub %s",
                hub_id,
            )
            continue
        for raw_scene in response:
            if not isinstance(raw_scene, dict):
                _LOGGER.debug(
                    "Ignoring invalid LifeSmart scene entry for hub %s", hub_id
                )
                continue
            raw_scene_id = raw_scene.get("id")
            if raw_scene_id is None:
                _LOGGER.debug(
                    "Ignoring LifeSmart scene without an ID for hub %s", hub_id
                )
                continue
            scene_id = str(raw_scene_id).strip()
            if not scene_id:
                continue
            scene_key = (hub_id, scene_id)
            if scene_key in seen_scene_keys:
                _LOGGER.debug(
                    "Ignoring duplicate LifeSmart scene %s for hub %s",
                    scene_id,
                    hub_id,
                )
                continue
            seen_scene_keys.add(scene_key)
            raw_name = raw_scene.get("name")
            name = str(raw_name).strip() if raw_name is not None else ""
            scenes.append(
                {
                    HUB_ID_KEY: hub_id,
                    "id": scene_id,
                    "name": name or f"LifeSmart Scene {scene_id}",
                }
            )
    return scenes


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):  # noqa: C901
    """Initialize a setup of the lifesamrt addon."""
    hass.data.setdefault(DOMAIN, {})

    connection_type = config_entry.options.get(
        CONF_CONNECTION_TYPE,
        config_entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_CLOUD),
    )
    is_local = connection_type == CONNECTION_TYPE_LOCAL
    app_key = config_entry.data.get(CONF_LIFESMART_APPKEY)
    app_key = config_entry.options.get(CONF_LIFESMART_APPKEY, app_key)
    app_token = config_entry.options.get(
        CONF_LIFESMART_APPTOKEN, config_entry.data.get(CONF_LIFESMART_APPTOKEN)
    )
    user_id = config_entry.options.get(
        CONF_LIFESMART_USERID, config_entry.data.get(CONF_LIFESMART_USERID)
    )
    user_password = config_entry.options.get(
        CONF_LIFESMART_USERPASSWORD, config_entry.data.get(CONF_LIFESMART_USERPASSWORD)
    )
    region = normalize_lifesmart_region(
        config_entry.options.get(CONF_REGION, config_entry.data.get(CONF_REGION))
    )
    exclude_devices = config_entry.options.get(
        CONF_EXCLUDE_ITEMS, config_entry.data.get(CONF_EXCLUDE_ITEMS)
    )
    exclude_hubs = config_entry.options.get(
        CONF_EXCLUDE_AGTS, config_entry.data.get(CONF_EXCLUDE_AGTS)
    )
    ai_include_hubs = config_entry.options.get(
        CONF_AI_INCLUDE_AGTS, config_entry.data.get(CONF_AI_INCLUDE_AGTS)
    )
    ai_include_items = config_entry.options.get(
        CONF_AI_INCLUDE_ITEMS, config_entry.data.get(CONF_AI_INCLUDE_ITEMS)
    )

    # default data
    if exclude_devices is None:
        exclude_devices = []
    if exclude_hubs is None:
        exclude_hubs = []
    if ai_include_hubs is None:
        ai_include_hubs = []
    if ai_include_items is None:
        ai_include_items = []

    if is_local:
        lifesmart_client = LocalLifeSmartClient(
            config_entry.options.get(
                CONF_HOST, config_entry.data.get(CONF_HOST)
            ),
            config_entry.options.get(
                CONF_PORT, config_entry.data.get(CONF_PORT, DEFAULT_LOCAL_PORT)
            ),
            config_entry.options.get(
                CONF_LOCAL_PASSWORD,
                config_entry.data.get(
                    CONF_LOCAL_PASSWORD, DEFAULT_LOCAL_PASSWORD
                ),
            ),
        )
    else:
        lifesmart_client = LifeSmartClient(
            region,
            app_key,
            app_token,
            user_id,
            user_password,
        )

    try:
        response = await lifesmart_client.login_async()
    except Exception as err:
        if is_local:
            await lifesmart_client.async_close()
        raise ConfigEntryNotReady("Unable to connect to LifeSmart") from err
    if response.get("code") != "success":
        if is_local:
            await lifesmart_client.async_close()
        raise ConfigEntryAuthFailed("LifeSmart rejected the configured credentials")

    try:
        devices = await lifesmart_client.get_all_device_async()
    except Exception as err:
        if is_local:
            await lifesmart_client.async_close()
        raise ConfigEntryNotReady("Unable to retrieve LifeSmart devices") from err
    if not isinstance(devices, list):
        if is_local:
            await lifesmart_client.async_close()
        raise ConfigEntryNotReady("LifeSmart device discovery failed")

    # Work with local copies because Home Assistant registry metadata is not part of
    # the LifeSmart API response.
    devices = [dict(device) for device in devices]

    try:
        hubs = await lifesmart_client.get_all_hubs_async()
    except Exception as err:  # Hub metadata must not block existing device setup.
        _LOGGER.warning("Unable to retrieve LifeSmart hub details: %s", type(err).__name__)
        hubs = []
    if not isinstance(hubs, list):
        _LOGGER.warning("LifeSmart hub discovery returned an invalid response")
        hubs = []
    hubs_by_id = {
        hub[HUB_ID_KEY]: dict(hub)
        for hub in hubs
        if isinstance(hub, dict) and hub.get(HUB_ID_KEY)
    }

    # Create hub devices
    dev_reg = device_registry.async_get(hass)
    hub_ids = set(device[HUB_ID_KEY] for device in devices) | set(hubs_by_id)
    for hub_id in hub_ids:
        hubs_by_id.setdefault(hub_id, {HUB_ID_KEY: hub_id})

    async def async_enrich_hub(hub):
        """Add non-sensitive cloud metadata without blocking hub discovery."""
        hub_id = hub[HUB_ID_KEY]
        system_info, timezone = await asyncio.gather(
            lifesmart_client.get_hub_system_info_async(hub_id),
            lifesmart_client.get_hub_timezone_async(hub_id),
            return_exceptions=True,
        )
        if isinstance(system_info, dict) and system_info.get("code") is None:
            mac = system_info.get("mac")
            if isinstance(mac, str) and re.fullmatch(
                r"(?:[0-9A-Fa-f]{2}[:-]?){5}[0-9A-Fa-f]{2}", mac
            ):
                hub["mac"] = device_registry.format_mac(mac)
            ip = system_info.get("ip")
            try:
                hub["ip"] = str(ip_address(ip))
            except ValueError:
                pass
        if isinstance(timezone, dict) and timezone.get("code") is None:
            if "tmzone" in timezone:
                hub["tmzone"] = timezone["tmzone"]

    await asyncio.gather(*(async_enrich_hub(hub) for hub in hubs_by_id.values()))

    scenes = await _async_discover_scenes(lifesmart_client, hub_ids, exclude_hubs)

    hub_device_registry_ids = {}
    for hub_id in hub_ids:
        hub = hubs_by_id[hub_id]
        mac = hub.get("mac")
        connection_info = {}
        if mac is not None:
            connection_info["connections"] = {
                (device_registry.CONNECTION_NETWORK_MAC, mac)
            }
        hub_device = dev_reg.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, hub_id)},
            name=hub.get("name") or "LifeSmart Hub",
            manufacturer="LifeSmart",
            model="Hub",
            sw_version=hub.get("agt_ver"),
            **connection_info,
        )
        hub_device_registry_ids[hub_id] = hub_device.id

    for device in devices:
        device[HUB_DEVICE_REGISTRY_ID_KEY] = hub_device_registry_ids[
            device[HUB_ID_KEY]
        ]

    _migrate_legacy_device_identifiers(dev_reg, config_entry.entry_id, devices)

    _cleanup_legacy_doorlock_history_entities(hass, devices)

    # Register only after setup succeeds so retries do not leak listeners.
    update_listener = config_entry.add_update_listener(_async_update_listener)

    runtime_data = LifeSmartRuntimeData(
        client=lifesmart_client,
        devices=devices,
        hubs=list(hubs_by_id.values()),
        scenes=scenes,
        exclude_devices=exclude_devices,
        exclude_hubs=exclude_hubs,
        ai_include_hubs=ai_include_hubs,
        ai_include_items=ai_include_items,
        update_listener=update_listener,
        device_availability={
            (device[HUB_ID_KEY], device[DEVICE_ID_KEY]): device.get("stat", 1) == 1
            for device in devices
            if device.get(HUB_ID_KEY) is not None
            and device.get(DEVICE_ID_KEY) is not None
        },
    )
    config_entry.runtime_data = runtime_data

    def data_update_handler(msg):  # noqa: C901
        data = msg["msg"]
        device_type = data[DEVICE_TYPE_KEY]
        hub_id = data[HUB_ID_KEY]
        device_id = data.get(DEVICE_ID_KEY)
        sub_device_key = data[SUBDEVICE_INDEX_KEY]

        if sub_device_key == "s" and "info" not in data:
            event_value = data.get("v")
            if device_type == "agt":
                if event_value == 2:
                    runtime_data.set_hub_devices_unavailable(hub_id)
                return
            if device_type not in ("ai", "elog") and device_id is not None:
                if event_value in (1, 2):
                    runtime_data.set_device_available(
                        hub_id, device_id, event_value == 1
                    )
                return

        if device_id is not None and sub_device_key != "s":
            runtime_data.set_device_available(hub_id, device_id, True)

        if (
            sub_device_key != "s"
            and device_id not in exclude_devices
            and hub_id not in exclude_hubs
        ):
            entity_id = generate_entity_id(
                device_type, hub_id, device_id, sub_device_key
            )

            if device_type in NATURE_TYPES and sub_device_key in [
                "P1",
                "P4",
                "P7",
                "P8",
                "P9",
                "P10",
            ]:
                raw_device = _find_device(devices, hub_id, device_id)
                if raw_device and is_nature_thermostat(raw_device):
                    climate_entity_id = generate_entity_id(
                        device_type, hub_id, device_id, NATURE_CLIMATE_KEY
                    )
                    dispatcher_send(
                        hass,
                        f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{climate_entity_id}",
                        data,
                    )
                    return
                if sub_device_key == "P4":
                    dispatcher_send(
                        hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                    )
                    return

            if (  # noqa: SIM114
                device_type in SUPPORTED_SWTICH_TYPES
                and sub_device_key in SUPPORTED_SUB_SWITCH_TYPES
                or device_type in AIR_PURIFIER_TYPES
                and sub_device_key == "O"
                or device_type in GENERIC_CONTROLLER_TYPES
                and sub_device_key
                in (
                    HA_CONTROLLER_SWITCH_PORTS
                    if device_type == "SL_JEMA"
                    else GENERIC_CONTROLLER_SWITCH_PORTS
                )
                or device_type in MODBUS_CONTROLLER_TYPES
                and (
                    sub_device_key == "O"
                    or sub_device_key.startswith("L")
                    and sub_device_key[1:].isdigit()
                )
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif (
                device_type in GENERIC_CONTROLLER_TYPES
                and sub_device_key in GENERIC_CONTROLLER_BINARY_PORTS
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in GENERIC_CONTROLLER_TYPES and sub_device_key == "P1":
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in SPOT_IR_TYPES and sub_device_key == "P2":
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in SMART_CAMERA_TYPES:
                if sub_device_key in ["M", "V"]:
                    dispatcher_send(
                        hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                    )
                elif sub_device_key == SMART_CAMERA_STATUS_EVENT_KEY:
                    for status_key in SMART_CAMERA_STATUS_BINARY_KEYS:
                        status_entity_id = generate_entity_id(
                            device_type, hub_id, device_id, status_key
                        )
                        dispatcher_send(
                            hass,
                            f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{status_entity_id}",
                            data,
                        )
            elif (
                device_type in BINARY_SENSOR_TYPES
                and sub_device_key in SUPPORTED_SUB_BINARY_SENSORS
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in WATER_LEAK_SENSOR_TYPES:
                if sub_device_key == "WA":
                    dispatcher_send(
                        hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                    )
                elif sub_device_key == "V":
                    dispatcher_send(hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data)
            elif (
                device_type in RADAR_MOTION_SENSOR_TYPES
                and sub_device_key == "P1"
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in DEFED_SENSOR_TYPES:
                if (
                    device_type in DEFED_DOOR_SENSOR_TYPES
                    and sub_device_key in ["GA", "A2", "TR"]
                    or device_type in DEFED_MOTION_SENSOR_TYPES
                    and sub_device_key in ["M", "TR"]
                    or device_type in DEFED_SIREN_TYPES
                    and sub_device_key in ["SR", "TR"]
                    or device_type in DEFED_KEYFOB_TYPES
                    and sub_device_key in ["eB1", "eB2", "eB3", "eB4"]
                ):
                    dispatcher_send(
                        hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                    )
                elif sub_device_key in ["T", "V"]:
                    dispatcher_send(
                        hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                    )
            elif (
                device_type in CO2_SENSOR_TYPES
                and sub_device_key in ["P1", "P2", "P3", "P4"]
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in ENV_SENSOR_TYPES and sub_device_key in [
                "T",
                "H",
                "Z",
                "V",
            ]:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in TVOC_CO2_SENSOR_TYPES and sub_device_key in [
                "P1",
                "P2",
                "P3",
                "P4",
                "P5",
                "P6",
            ]:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif (
                device_type == "SL_SC_CM"
                and sub_device_key == "P3"
                or device_type in SMOKE_SENSOR_TYPES
                and sub_device_key == "P2"
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in NOISE_SENSOR_TYPES:
                if sub_device_key in ["P1", "P2", "P3", "P4"]:
                    dispatcher_send(
                        hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                    )
            elif device_type in GAS_SENSOR_TYPES and sub_device_key in ["P1", "P2", "P3"]:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in SMART_ALARM_TYPES and sub_device_key in ["P1", "P2"]:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in ELECTRICITY_METER_TYPES and sub_device_key == "EPA":
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in DLT_METER_TYPES and sub_device_key in ["EE", "EP"]:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in MODBUS_CONTROLLER_TYPES and (
                sub_device_key
                in [
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
                ]
                or sub_device_key.startswith(("EE", "EP", "EPF", "EF", "EI", "EV"))
                and sub_device_key[-1].isdigit()
                or sub_device_key.startswith("PM")
                and sub_device_key[2:].isdigit()
            ):
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in AIR_PURIFIER_TYPES and sub_device_key in [
                "RM",
                "T",
                "H",
                "PM",
                "FL",
                "UV",
            ]:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )

            elif (
                device_type in COVER_TYPES
                and device_type not in GARAGE_DOOR_TYPES
                and sub_device_key == "P1"
                or device_type in GARAGE_DOOR_TYPES
                and sub_device_key == "P2"
            ):
                dispatcher_send(hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data)
            elif device_type in EV_SENSOR_TYPES:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in GAS_SENSOR_TYPES and data["val"] > 0:
                dispatcher_send(hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data)
            elif device_type in SPOT_TYPES or device_type in LIGHT_SWITCH_TYPES:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in LIGHT_DIMMER_TYPES:
                dispatcher_send(hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data)

            elif device_type in CLIMATE_TYPES:
                dispatcher_send(
                    hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data
                )
            elif device_type in LOCK_TYPES:
                if sub_device_key in [
                    DIGITAL_DOORLOCK_BATTERY_EVENT_KEY,
                    DIGITAL_DOORLOCK_ALARM_EVENT_KEY,
                    DIGITAL_DOORLOCK_LOCK_EVENT_KEY,
                    DIGITAL_DOORLOCK_DOORBELL_EVENT_KEY,
                    DIGITAL_DOORLOCK_OPERATION_EVENT_KEY,
                    DIGITAL_DOORLOCK_HISTORY_LOCK_EVENT_KEY,
                ]:
                    _dispatch_doorlock_update(
                        hass,
                        device_type,
                        hub_id,
                        device_id,
                        sub_device_key,
                        entity_id,
                        data,
                    )
            elif device_type in OT_SENSOR_TYPES and sub_device_key in [
                "Z",
                "V",
                "P3",
                "P4",
            ]:
                dispatcher_send(hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data)
            elif device_type in SMART_PLUG_TYPES:
                if (
                    sub_device_key.startswith("O")
                    or sub_device_key in ["P1", "P2", "P3"]
                    or device_type in SMART_PLUG_ENERGY_TYPES
                    and sub_device_key == "EE1"
                ):
                    dispatcher_send(hass, f"{LIFESMART_SIGNAL_UPDATE_ENTITY}_{entity_id}", data)
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
        data_update_handler(msg)

    def on_error(ws, error):
        if runtime_data.connected:
            _LOGGER.warning("LifeSmart websocket connection lost: %s", error)
        runtime_data.set_connected(False, type(error).__name__)

    def on_close(ws, close_status_code, close_msg):
        runtime_data.set_connected(False, f"closed:{close_status_code}")
        _LOGGER.debug(
            "lifesmart websocket closed...: %s %s",
            str(close_status_code),
            str(close_msg),
        )

    def on_open(ws):
        was_unavailable = runtime_data.last_error is not None
        runtime_data.set_connected(True)
        client = runtime_data.client
        send_data = client.generate_wss_auth()
        ws.send(send_data)
        if was_unavailable:
            _LOGGER.info("LifeSmart websocket connection restored")
            hass.loop.call_soon_threadsafe(
                lambda: hass.async_create_task(
                    _async_refresh_device_availability(runtime_data),
                    "Refresh LifeSmart device availability",
                )
            )
        _LOGGER.debug("LifeSmart websocket sending_data")

    if is_local:
        lifesmart_client.start_listener(
            data_update_handler,
            lambda connected, error: runtime_data.set_connected(connected, error),
        )
    else:
        ws = websocket.WebSocketApp(
            lifesmart_client.get_wss_url(),
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        state_manager = LifeSmartStatesManager(ws=ws)
        runtime_data.state_manager = state_manager
        state_manager.start_keep_alive()

    await hass.config_entries.async_forward_entry_setups(
        config_entry, _platforms_for_client(lifesmart_client)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, _platforms_for_client(entry.runtime_data.client)
    )

    if not unload_ok:
        return False

    runtime_data = entry.runtime_data
    state_manager = runtime_data.state_manager
    if state_manager is not None:
        await hass.async_add_executor_job(state_manager.stop_keep_alive)
    if getattr(runtime_data.client, "is_local", False):
        await runtime_data.client.async_close()

    update_listener = runtime_data.update_listener
    if callable(update_listener):
        update_listener()

    return True


async def _async_update_listener(hass: HomeAssistant, config_entry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)


def device_via_info(raw_device_data: dict, hub_id: str) -> dict:
    """Return hub topology info supported by the running Home Assistant."""
    hub_device_id = raw_device_data.get(HUB_DEVICE_REGISTRY_ID_KEY)
    if hub_device_id is not None and "via_device_id" in DeviceInfo.__annotations__:
        return {"via_device_id": hub_device_id}
    return {"via_device": (DOMAIN, hub_id)}


def device_identifier(hub_id: str, device_id: str) -> tuple[str, str]:
    """Return a valid, integration-scoped identifier for a LifeSmart device."""
    return (DOMAIN, f"{hub_id}:{device_id}")


def _migrate_legacy_device_identifiers(
    dev_reg, config_entry_id: str, devices: list[dict]
) -> None:
    """Replace legacy three-part identifiers without replacing device entries."""
    replacements = {
        (DOMAIN, device[HUB_ID_KEY], device[DEVICE_ID_KEY]): device_identifier(
            device[HUB_ID_KEY], device[DEVICE_ID_KEY]
        )
        for device in devices
        if DEVICE_ID_KEY in device
    }
    if not replacements:
        return

    for device_entry in list(getattr(dev_reg, "devices", {}).values()):
        owner = getattr(device_entry, "config_entry_id", None)
        if owner is not None:
            belongs_to_entry = owner == config_entry_id
        else:
            belongs_to_entry = config_entry_id in device_entry.config_entries
        if not belongs_to_entry:
            continue

        migrated_identifiers = {
            replacements.get(identifier, identifier)
            for identifier in device_entry.identifiers
        }
        if migrated_identifiers != device_entry.identifiers:
            dev_reg.async_update_device(
                device_entry.id, new_identifiers=migrated_identifiers
            )


class LifeSmartDevice(LifeSmartAvailabilityMixin, Entity):
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
        return await self._client.send_epset_async(type, val, idx, agt, me)

    async def async_lifesmart_epget(self):
        """Get lifesmart device info."""
        agt = self._agt
        me = self._me
        return await self._client.get_epget_async(agt, me)


class LifeSmartStatesManager(threading.Thread):
    """Instance to manage websocket to get push data from LifeSmart service."""

    def __init__(self, ws) -> None:
        """Init LifeSmart Update Manager."""
        threading.Thread.__init__(self, daemon=True)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._ws = ws

    def run(self):  # noqa: D102
        while not self._stop_event.is_set():
            _LOGGER.debug("lifesmart: starting wss")
            self._ws.run_forever()
            _LOGGER.debug("lifesmart: restart wss")
            self._stop_event.wait(10)

    def start_keep_alive(self):
        """Start keep alive mechanism."""
        with self._lock:
            self._stop_event.clear()
            threading.Thread.start(self)

    def stop_keep_alive(self):
        """Stop keep alive mechanism."""
        with self._lock:
            self._stop_event.set()
            self._ws.close()
        if self.is_alive() and threading.current_thread() is not self:
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
    if device_type in NATURE_TYPES and sub_device == NATURE_CLIMATE_KEY:
        return Platform.CLIMATE
    elif device_type in NATURE_TYPES and sub_device == "P4":
        return Platform.SENSOR
    elif device_type in NATURE_TYPES and sub_device in NATURE_SWITCH_PORTS:
        return Platform.SWITCH
    elif device_type in SPOT_TYPES and sub_device == "climate_ac":
        return Platform.CLIMATE
    elif device_type in SPOT_TYPES and sub_device == "remote":
        return Platform.REMOTE
    if device_type in SUPPORTED_SWTICH_TYPES:
        return Platform.SWITCH
    elif device_type in AIR_PURIFIER_TYPES and sub_device == "O":
        return Platform.SWITCH
    elif device_type in GENERIC_CONTROLLER_TYPES and sub_device in (
        HA_CONTROLLER_SWITCH_PORTS
        if device_type == "SL_JEMA"
        else GENERIC_CONTROLLER_SWITCH_PORTS
    ):
        return Platform.SWITCH
    elif device_type in MODBUS_CONTROLLER_TYPES and sub_device and (
        sub_device == "O" or sub_device.startswith("L") and sub_device[1:].isdigit()
    ):
        return Platform.SWITCH
    elif (
        device_type in GENERIC_CONTROLLER_TYPES
        and sub_device in GENERIC_CONTROLLER_BINARY_PORTS
    ):
        return Platform.BINARY_SENSOR
    elif device_type in GENERIC_CONTROLLER_TYPES and sub_device == "P1":
        return Platform.SENSOR
    elif device_type in SPOT_IR_TYPES and sub_device == "P2":
        return Platform.BINARY_SENSOR
    elif device_type in WATER_LEAK_SENSOR_TYPES and sub_device == "WA":
        return Platform.BINARY_SENSOR
    elif device_type in WATER_LEAK_SENSOR_TYPES and sub_device == "V":
        return Platform.SENSOR
    elif device_type in RADAR_MOTION_SENSOR_TYPES and sub_device == "P1":
        return Platform.BINARY_SENSOR
    elif (
        device_type in DEFED_DOOR_SENSOR_TYPES
        and sub_device in ["GA", "A2", "TR"]
        or device_type in DEFED_MOTION_SENSOR_TYPES
        and sub_device in ["M", "TR"]
        or device_type in DEFED_SIREN_TYPES
        and sub_device in ["SR", "TR"]
        or device_type in DEFED_KEYFOB_TYPES
        and sub_device in ["eB1", "eB2", "eB3", "eB4"]
    ):
        return Platform.BINARY_SENSOR
    elif device_type in DEFED_SENSOR_TYPES and sub_device in ["T", "V"]:
        return Platform.SENSOR
    elif device_type in CO2_SENSOR_TYPES:
        return Platform.SENSOR
    elif device_type in NOISE_SENSOR_TYPES and sub_device in ["P1", "P2", "P4"]:
        return Platform.SENSOR
    elif device_type in NOISE_SENSOR_TYPES and sub_device == "P3":
        return Platform.BINARY_SENSOR
    elif device_type in GAS_SENSOR_TYPES and sub_device == "P3":
        return Platform.BINARY_SENSOR
    elif device_type in SMART_ALARM_TYPES and sub_device in ["P1", "P2"]:
        return Platform.BINARY_SENSOR
    elif device_type in SMART_CAMERA_TYPES and sub_device in [
        "M",
        *SMART_CAMERA_STATUS_BINARY_KEYS,
    ]:
        return Platform.BINARY_SENSOR
    elif device_type in SMART_CAMERA_TYPES and sub_device == "V":
        return Platform.SENSOR
    elif (
        device_type == "SL_SC_CM"
        and sub_device == "P3"
        or device_type in SMOKE_SENSOR_TYPES
        and sub_device == "P2"
    ):
        return Platform.SENSOR
    elif device_type in OT_SENSOR_TYPES and sub_device in ["Z", "V", "P3", "P4"]:
        return Platform.SENSOR
    elif device_type in BINARY_SENSOR_TYPES:
        return Platform.BINARY_SENSOR
    elif device_type in COVER_TYPES:
        return Platform.COVER
    elif (
        device_type
        in EV_SENSOR_TYPES + GAS_SENSOR_TYPES + OT_SENSOR_TYPES + ELECTRICITY_METER_TYPES
        or device_type in AIR_PURIFIER_TYPES
        and sub_device in ["RM", "T", "H", "PM", "FL", "UV"]
        or device_type in DLT_METER_TYPES
        and sub_device in ["EE", "EP"]
        or device_type in MODBUS_CONTROLLER_TYPES
        and sub_device
        and (
            sub_device
            in [
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
            ]
            or sub_device.startswith(("EE", "EP", "EPF", "EF", "EI", "EV"))
            and sub_device[-1].isdigit()
            or sub_device.startswith("PM")
            and sub_device[2:].isdigit()
        )
    ):
        return Platform.SENSOR
    elif device_type in SPOT_TYPES + LIGHT_SWITCH_TYPES + LIGHT_DIMMER_TYPES:
        return Platform.LIGHT
    elif device_type in CLIMATE_TYPES:
        return Platform.CLIMATE
    elif device_type in LOCK_TYPES and sub_device == DIGITAL_DOORLOCK_BATTERY_EVENT_KEY:
        return Platform.SENSOR
    elif device_type in LOCK_TYPES and sub_device == DIGITAL_DOORLOCK_OPERATION_EVENT_KEY:
        return Platform.SENSOR
    elif (
        device_type in LOCK_TYPES
        and sub_device == DIGITAL_DOORLOCK_LOCK_EVENT_KEY
        or device_type in LOCK_TYPES
        and sub_device == DIGITAL_DOORLOCK_ALARM_EVENT_KEY
        or device_type in LOCK_TYPES
        and sub_device == DIGITAL_DOORLOCK_DOORBELL_EVENT_KEY
    ):
        return Platform.BINARY_SENSOR
    elif device_type in LOCK_TYPES and sub_device == DIGITAL_DOORLOCK_HISTORY_LOCK_EVENT_KEY:
        return Platform.SENSOR
    elif device_type in LOCK_TYPES and sub_device == "ALM_DESC":
        return Platform.SENSOR
    elif device_type in SMART_PLUG_TYPES and (
        sub_device == "P1"
        or sub_device
        and sub_device.startswith("O")
    ):
        return Platform.SWITCH
    elif device_type in SMART_PLUG_TYPES and sub_device in ["P2", "P3"]:
        return Platform.SENSOR
    elif device_type in SMART_PLUG_ENERGY_TYPES and sub_device == "EE1":
        return Platform.SENSOR
    return ""


def _cleanup_legacy_doorlock_history_entities(hass, devices):
    """Remove old binary_sensor HISLK entries after moving HISLK to sensor."""
    ent_reg = entity_registry.async_get(hass)
    for device in devices:
        if device.get(DEVICE_TYPE_KEY) not in LOCK_TYPES:
            continue
        data = device.get("data", {})
        if DIGITAL_DOORLOCK_HISTORY_LOCK_EVENT_KEY not in data:
            continue
        legacy_object_id = (
            device[DEVICE_TYPE_KEY]
            + "_"
            + device[HUB_ID_KEY].replace("__", "_")
            + "_"
            + device[DEVICE_ID_KEY]
            + "_"
            + DIGITAL_DOORLOCK_HISTORY_LOCK_EVENT_KEY
        )
        legacy_entity_id = (Platform.BINARY_SENSOR + "." + legacy_object_id).lower()
        legacy_entity_id = legacy_entity_id.replace(":", "_").replace("@", "_").replace(
            "-", "_"
        )
        if ent_reg.async_get(legacy_entity_id):
            ent_reg.async_remove(legacy_entity_id)


def _sanitize_entity_id_part(value):
    """Return a Home Assistant entity id-safe object id part."""
    return re.sub(r"_+", "_", re.sub(r"[^0-9a-zA-Z_]+", "_", str(value))).strip(
        "_"
    )


def configure_entity_identity(
    entity: Entity, unique_id: str, suggested_entity_id: str | None = None
) -> str:
    """Configure registry-owned identity while preserving existing unique IDs."""
    _, object_id = (suggested_entity_id or unique_id).split(".", 1)
    entity._attr_unique_id = unique_id
    entity._attr_suggested_object_id = object_id
    return unique_id


def generate_entity_id(
    device_type, hub_id, device_id, idx=None, fallback_platform=None
):
    """Generate unique id for entity in HA."""
    raw_device_type = device_type
    raw_sub_device = idx
    device_type = _sanitize_entity_id_part(device_type)
    hub_id = _sanitize_entity_id_part(hub_id)
    device_id = _sanitize_entity_id_part(device_id)
    if idx:
        sub_device = _sanitize_entity_id_part(idx)
    else:
        sub_device = None

    if device_type in NATURE_TYPES and sub_device == NATURE_CLIMATE_KEY:
        return Platform.CLIMATE + (
            "." + device_type + "_" + hub_id + "_" + device_id + "_thermostat"
        ).lower()

    if device_type in SPOT_TYPES and sub_device == "remote":
        return Platform.REMOTE + (
            "." + device_type + "_" + hub_id + "_" + device_id + "_remote"
        ).lower()

    if device_type in SPOT_TYPES and sub_device == "climate_ac":
        return Platform.CLIMATE + (
            "." + device_type + "_" + hub_id + "_" + device_id + "_climate_ac"
        ).lower()

    if raw_device_type in [  # noqa: RET503
        *SUPPORTED_SWTICH_TYPES,
        *AIR_PURIFIER_TYPES,
        *GENERIC_CONTROLLER_TYPES,
        *DLT_METER_TYPES,
        *MODBUS_CONTROLLER_TYPES,
        *BINARY_SENSOR_TYPES,
        *EV_SENSOR_TYPES,
        *GAS_SENSOR_TYPES,
        *ELECTRICITY_METER_TYPES,
        *SPOT_TYPES,
        *LIGHT_SWITCH_TYPES,
        *OT_SENSOR_TYPES,
        *SMART_PLUG_TYPES,
        *LOCK_TYPES,
        *WATER_LEAK_SENSOR_TYPES,
        *RADAR_MOTION_SENSOR_TYPES,
        *DEFED_SENSOR_TYPES,
        *CO2_SENSOR_TYPES,
        *SMOKE_SENSOR_TYPES,
        *NOISE_SENSOR_TYPES,
        *SMART_ALARM_TYPES,
        *SMART_CAMERA_TYPES,
    ]:
        if sub_device:
            return (
                get_platform_by_device(raw_device_type, raw_sub_device)
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

        return (
            # no sub device (idx)
            get_platform_by_device(raw_device_type)
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
        ).lower()

    if fallback_platform:
        suffix = f"_{sub_device}" if sub_device else ""
        return (
            f"{fallback_platform}.{device_type}_{hub_id}_{device_id}{suffix}"
        ).lower()


def _find_device(devices, hub_id, device_id):
    """Find a LifeSmart raw device by hub and device id."""
    return next(
        (
            device
            for device in devices
            if device.get(HUB_ID_KEY) == hub_id
            and device.get(DEVICE_ID_KEY) == device_id
        ),
        None,
    )
