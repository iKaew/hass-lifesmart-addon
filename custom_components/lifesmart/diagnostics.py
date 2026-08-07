"""Diagnostics support for LifeSmart."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_LIFESMART_APPKEY,
    CONF_LIFESMART_APPTOKEN,
    CONF_LIFESMART_USERID,
    CONF_LIFESMART_USERPASSWORD,
    DEVICE_TYPE_KEY,
)
from .runtime_data import LifeSmartRuntimeData

TO_REDACT = {
    CONF_LIFESMART_APPKEY,
    CONF_LIFESMART_APPTOKEN,
    CONF_LIFESMART_USERID,
    CONF_LIFESMART_USERPASSWORD,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry
) -> dict[str, Any]:
    """Return privacy-safe diagnostics for a LifeSmart entry."""
    runtime: LifeSmartRuntimeData = entry.runtime_data
    device_types = Counter(
        device.get(DEVICE_TYPE_KEY, "unknown") for device in runtime.devices
    )
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "connection": {
            "connected": runtime.connected,
            "last_error": runtime.last_error,
        },
        "devices": {
            "count": len(runtime.devices),
            "types": dict(sorted(device_types.items())),
            "excluded_device_count": len(runtime.exclude_devices),
            "excluded_hub_count": len(runtime.exclude_hubs),
        },
    }
