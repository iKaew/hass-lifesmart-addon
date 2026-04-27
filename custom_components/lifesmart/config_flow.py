"""lifesmart by @ikaew."""

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_REGION
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import selector

from .const import (
    CONF_AC_CONFIG,
    CONF_LIFESMART_APPKEY,
    CONF_LIFESMART_APPTOKEN,
    CONF_LIFESMART_USERID,
    CONF_LIFESMART_USERPASSWORD,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DOMAIN,
    HUB_ID_KEY,
    IR_CATEGORY_AC,
    LIFESMART_REGION_OPTIONS,
    SPOT_TYPES,
    normalize_lifesmart_region,
)
from .lifesmart_client import LifeSmartClient

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = {
    vol.Required(CONF_LIFESMART_APPKEY): str,
    vol.Required(CONF_LIFESMART_APPTOKEN): str,
    vol.Required(CONF_LIFESMART_USERID): str,
    vol.Required(CONF_LIFESMART_USERPASSWORD): str,
    vol.Required(CONF_REGION): selector(LIFESMART_REGION_OPTIONS),
}


async def validate_input(hass, data):
    """Validate the user input allows us to connect."""

    app_key = data[CONF_LIFESMART_APPKEY]
    app_token = data[CONF_LIFESMART_APPTOKEN]
    user_id = data[CONF_LIFESMART_USERID]
    user_password = data[CONF_LIFESMART_USERPASSWORD]
    region = normalize_lifesmart_region(data[CONF_REGION])

    lifesmart_client = LifeSmartClient(
        region,
        app_key,
        app_token,
        user_id,
        user_password,
    )

    response = await lifesmart_client.login_async()
    if response["code"] != "success":
        raise Exception(f"Error connecting to LifeSmart API: {response}")

    response = await lifesmart_client.get_all_device_async()
    if "code" in response:
        raise Exception(f"Error connecting to LifeSmart API: {response}")

    return {"title": f"User Id {user_id}", "unique_id": app_key}


def get_unique_id(wiser_id: str):
    """Generate Unique ID for Hub."""
    return str(f"{DOMAIN}-{wiser_id}")


@config_entries.HANDLERS.register(DOMAIN)
class LifeSmartConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """LifeSmartConfigFlowHandler configuration method."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_PUSH

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.discovery_info = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return LifeSmartOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a config flow."""
        errors = {}
        if user_input is not None:
            try:
                validated = await validate_input(self.hass, user_input)
            except Exception as err:
                _LOGGER.error("Input validation error %s", err)
                errors["base"] = str(err)

            if "base" not in errors:
                await self.async_set_unique_id(validated["unique_id"])
                self._abort_if_unique_id_configured()

                # Add hub name to config
                user_input[CONF_NAME] = validated["title"]

                return self.async_create_entry(
                    title=validated["title"], data=user_input
                )
        # If we are here, the user input is invalid or not provided
        # Pre-fill the form with the previously entered data if available
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_LIFESMART_APPKEY,
                    default=user_input.get(CONF_LIFESMART_APPKEY, "")
                    if user_input
                    else "",
                ): str,
                vol.Required(
                    CONF_LIFESMART_APPTOKEN,
                    default=user_input.get(CONF_LIFESMART_APPTOKEN, "")
                    if user_input
                    else "",
                ): str,
                vol.Required(
                    CONF_LIFESMART_USERID,
                    default=user_input.get(CONF_LIFESMART_USERID, "")
                    if user_input
                    else "",
                ): str,
                vol.Required(
                    CONF_LIFESMART_USERPASSWORD,
                    default=user_input.get(CONF_LIFESMART_USERPASSWORD, "")
                    if user_input
                    else "",
                ): str,
                vol.Required(
                    CONF_REGION,
                    default=user_input.get(CONF_REGION, "") if user_input else "",
                ): selector(LIFESMART_REGION_OPTIONS),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


class LifeSmartOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an option flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._config_entry = config_entry
        self._selected_device_key: str | None = None
        self._selected_brand: str | None = None
        self._client: LifeSmartClient | None = None
        self._remote_defaults: dict[str, dict[str, str]] = {}

    def _get_entry_value(self, key: str, default=None):
        """Return the effective entry value, preferring options."""
        return self._config_entry.options.get(
            key, self._config_entry.data.get(key, default)
        )

    async def _get_client(self) -> LifeSmartClient:
        """Create and authenticate a client for options-flow API calls."""
        if self._client is not None:
            return self._client

        client = LifeSmartClient(
            normalize_lifesmart_region(self._get_entry_value(CONF_REGION)),
            self._get_entry_value(CONF_LIFESMART_APPKEY),
            self._get_entry_value(CONF_LIFESMART_APPTOKEN),
            self._get_entry_value(CONF_LIFESMART_USERID),
            self._get_entry_value(CONF_LIFESMART_USERPASSWORD),
        )
        response = await client.login_async()
        if response["code"] != "success":
            raise ValueError(f"Error connecting to LifeSmart API: {response}")

        self._client = client
        return client

    def _get_spot_devices(self) -> list[dict]:
        """Return SPOT devices from the running config entry."""
        return [
            device
            for device in self.hass.data.get(DOMAIN, {})
            .get(self._config_entry.entry_id, {})
            .get("devices", [])
            if device.get(DEVICE_TYPE_KEY) in SPOT_TYPES
        ]

    def _normalize_brand_options(self, brands_data) -> dict[str, str]:
        """Convert brand data from the API into selector options."""
        options: dict[str, str] = {}

        if isinstance(brands_data, dict):
            items = brands_data.items()
        elif isinstance(brands_data, list):
            items = []
            for item in brands_data:
                if isinstance(item, dict):
                    code = str(
                        item.get("brand")
                        or item.get("id")
                        or item.get("value")
                        or item.get("name")
                    )
                    name = str(item.get("name") or item.get("title") or code)
                    items.append((code, name))
                else:
                    items.append((str(item), str(item)))
        else:
            items = []

        for code, value in items:
            if isinstance(value, dict):
                name = str(
                    value.get("name")
                    or value.get("title")
                    or value.get("brand")
                    or code
                )
            else:
                name = str(value)
            options[str(code)] = name

        return options

    def _normalize_remote_idx_options(self, remote_data) -> list[str]:
        """Convert remote index data from the API into selectable values."""
        if isinstance(remote_data, list):
            return [str(item.get("idx") if isinstance(item, dict) else item) for item in remote_data]
        if isinstance(remote_data, dict):
            return [str(value) for value in remote_data.values()]
        return []

    async def _get_device_remote_default(self, device_key: str) -> dict[str, str]:
        """Return the current AC remote assignment from the SPOT remote list."""
        if device_key in self._remote_defaults:
            return self._remote_defaults[device_key]

        result: dict[str, str] = {}
        try:
            hub_id, device_id = device_key.rsplit("_", 1)
            client = await self._get_client()
            remote_list = await client.get_ir_remote_list_async(hub_id)
            if isinstance(remote_list, dict):
                for ai, remote_info in remote_list.items():
                    if not isinstance(remote_info, dict):
                        continue

                    remote_category = str(remote_info.get("category", ""))
                    remote_brand = str(remote_info.get("brand", ""))
                    remote_idx = str(remote_info.get("idx", ""))
                    remote_me = str(
                        remote_info.get("me")
                        or remote_info.get("device_id")
                        or remote_info.get("dev")
                        or ""
                    )
                    device_matches = ai == device_id or device_id in ai or remote_me == device_id
                    if device_matches and remote_category == IR_CATEGORY_AC:
                        result = {
                            "category": remote_category,
                            "brand": remote_brand,
                            "idx": remote_idx,
                            "ai": str(ai),
                        }
                        break
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read current device AC remote defaults: %s", err)

        self._remote_defaults[device_key] = result
        return result

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a config flow."""
        errors = {}
        if user_input is not None:
            try:
                validated = await validate_input(self.hass, user_input)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Input validation error: %s", err)
                errors["base"] = str(err)

            if "base" not in errors:
                # Add hub name to config
                user_input[CONF_NAME] = validated["title"]

                return self.async_create_entry(
                    title=validated["title"], data=user_input
                )
        schema = {
            vol.Required(
                CONF_LIFESMART_APPKEY,
                default=self._get_entry_value(CONF_LIFESMART_APPKEY),
            ): str,
            vol.Required(
                CONF_LIFESMART_APPTOKEN,
                default=self._get_entry_value(CONF_LIFESMART_APPTOKEN),
            ): str,
            vol.Required(
                CONF_LIFESMART_USERID,
                default=self._get_entry_value(CONF_LIFESMART_USERID),
            ): str,
            vol.Required(
                CONF_LIFESMART_USERPASSWORD,
                default=self._get_entry_value(CONF_LIFESMART_USERPASSWORD),
            ): str,
            vol.Required(
                CONF_REGION,
                default=self._get_entry_value(CONF_REGION),
            ): selector(LIFESMART_REGION_OPTIONS),
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        menu_options = ["user", "ac_device"]
        if self._get_entry_value(CONF_AC_CONFIG, {}):
            menu_options.append("ac_remove")

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )

    async def async_step_ac_device(self, user_input=None):
        """Choose the SPOT device to configure."""
        spot_devices = self._get_spot_devices()
        if not spot_devices:
            return self.async_abort(reason="no_spot_devices")

        errors = {}

        if user_input is not None:
            self._selected_device_key = user_input["device"]
            remote_default = await self._get_device_remote_default(
                self._selected_device_key
            )
            if remote_default.get("category") != IR_CATEGORY_AC:
                errors["base"] = "no_ac_remote_assigned"
            else:
                ac_config = dict(self._get_entry_value(CONF_AC_CONFIG, {}))
                ac_config[self._selected_device_key] = {
                    "category": IR_CATEGORY_AC,
                    "brand": remote_default.get("brand", ""),
                    "idx": remote_default.get("idx", ""),
                    "ai": remote_default.get("ai", ""),
                }
                options = dict(self._config_entry.options)
                options[CONF_AC_CONFIG] = ac_config
                return self.async_create_entry(title="", data=options)

        device_options = []
        existing_ac_config = self._get_entry_value(CONF_AC_CONFIG, {})
        for device in spot_devices:
            hub_id = device.get(HUB_ID_KEY)
            device_id = device.get(DEVICE_ID_KEY)
            device_key = f"{hub_id}_{device_id}"
            current_brand = existing_ac_config.get(device_key, {}).get("brand")
            label = f"{device.get(DEVICE_NAME_KEY)} ({hub_id}/{device_id})"
            if current_brand:
                label += f" [{current_brand}]"
            device_options.append({"value": device_key, "label": label})

        schema = vol.Schema(
            {
                vol.Required("device"): selector(
                    {"select": {"options": device_options, "mode": "dropdown"}}
                )
            }
        )

        return self.async_show_form(
            step_id="ac_device",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_ac_brand(self, user_input=None):
        """Choose the AC brand for the selected SPOT device."""
        errors = {}
        if self._selected_device_key is None:
            return await self.async_step_ac_device()

        try:
            client = await self._get_client()
            brand_map = self._normalize_brand_options(
                await client.get_brands_async(IR_CATEGORY_AC)
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Unable to fetch AC brands: %s", err)
            brand_map = {}
            errors["base"] = str(err)

        if user_input is not None and "brand" in user_input:
            self._selected_brand = user_input["brand"]
            return await self.async_step_ac_remote()

        if not brand_map:
            return self.async_show_form(
                step_id="ac_brand",
                data_schema=vol.Schema({}),
                errors=errors or {"base": "no_ac_brands"},
            )

        existing_ac_config = self._get_entry_value(CONF_AC_CONFIG, {})
        remote_default = await self._get_device_remote_default(self._selected_device_key)
        current_brand = (
            remote_default.get("brand")
            or existing_ac_config.get(self._selected_device_key, {}).get("brand")
        )
        brand_options = [
            {"value": code, "label": f"{name} ({code})"}
            for code, name in sorted(brand_map.items(), key=lambda item: item[1].lower())
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    "brand",
                    default=current_brand if current_brand in brand_map else vol.UNDEFINED,
                ): selector({"select": {"options": brand_options, "mode": "dropdown"}})
            }
        )

        return self.async_show_form(
            step_id="ac_brand",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_ac_remote(self, user_input=None):
        """Choose the AC remote profile index for the selected brand."""
        errors = {}
        if self._selected_device_key is None:
            return await self.async_step_ac_device()
        if self._selected_brand is None:
            return await self.async_step_ac_brand()

        remote_default = await self._get_device_remote_default(self._selected_device_key)

        try:
            client = await self._get_client()
            remote_options = self._normalize_remote_idx_options(
                await client.get_remote_idxs_async(IR_CATEGORY_AC, self._selected_brand)
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Unable to fetch AC remote indexes: %s", err)
            remote_options = []
            errors["base"] = str(err)

        if user_input is not None:
            hub_id, device_id = self._selected_device_key.rsplit("_", 1)
            ai = None
            try:
                client = await self._get_client()
                ai = await client.resolve_ir_remote_ai_async(
                    hub_id,
                    device_id,
                    IR_CATEGORY_AC,
                    self._selected_brand,
                    user_input["idx"],
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Unable to resolve A/C remote ai: %s", err)

            ac_config = dict(self._get_entry_value(CONF_AC_CONFIG, {}))
            ac_config[self._selected_device_key] = {
                "category": IR_CATEGORY_AC,
                "brand": self._selected_brand,
                "idx": user_input["idx"],
                "ai": ai or remote_default.get("ai", ""),
            }
            options = dict(self._config_entry.options)
            options[CONF_AC_CONFIG] = ac_config
            return self.async_create_entry(title="", data=options)

        if not remote_options:
            return self.async_show_form(
                step_id="ac_remote",
                data_schema=vol.Schema({}),
                errors=errors or {"base": "no_remote_idxs"},
            )

        existing_ac_config = self._get_entry_value(CONF_AC_CONFIG, {})
        current_idx = (
            remote_default.get("idx")
            if self._selected_brand == remote_default.get("brand")
            else None
        ) or existing_ac_config.get(self._selected_device_key, {}).get("idx")
        selector_options = [
            {"value": idx, "label": idx}
            for idx in remote_options
            if idx
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    "idx",
                    default=current_idx
                    if current_idx in remote_options
                    else remote_options[0],
                ): selector(
                    {"select": {"options": selector_options, "mode": "dropdown"}}
                )
            }
        )

        return self.async_show_form(
            step_id="ac_remote",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_ac_remove(self, user_input=None):
        """Remove an existing SPOT A/C configuration."""
        ac_config = dict(self._get_entry_value(CONF_AC_CONFIG, {}))
        if not ac_config:
            return self.async_abort(reason="no_ac_config")

        spot_devices = {
            f"{device.get(HUB_ID_KEY)}_{device.get(DEVICE_ID_KEY)}": device
            for device in self._get_spot_devices()
        }

        if user_input is not None:
            device_key = user_input["device"]
            ac_config.pop(device_key, None)
            options = dict(self._config_entry.options)
            if ac_config:
                options[CONF_AC_CONFIG] = ac_config
            else:
                options.pop(CONF_AC_CONFIG, None)
            return self.async_create_entry(title="", data=options)

        device_options = []
        for device_key, ac_info in ac_config.items():
            device = spot_devices.get(device_key)
            if device is not None:
                label = (
                    f"{device.get(DEVICE_NAME_KEY)} "
                    f"({device.get(HUB_ID_KEY)}/{device.get(DEVICE_ID_KEY)})"
                )
            else:
                label = device_key

            brand = ac_info.get("brand")
            idx = ac_info.get("idx")
            if brand:
                label += f" [{brand}"
                if idx:
                    label += f" / {idx}"
                label += "]"

            device_options.append({"value": device_key, "label": label})

        schema = vol.Schema(
            {
                vol.Required("device"): selector(
                    {"select": {"options": device_options, "mode": "dropdown"}}
                )
            }
        )

        return self.async_show_form(step_id="ac_remove", data_schema=schema)
