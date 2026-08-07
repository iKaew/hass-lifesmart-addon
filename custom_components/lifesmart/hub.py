"""Shared support for LifeSmart hub entities."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import HUB_ID_KEY
from .runtime_data import LifeSmartRuntimeData

HUB_STATUS_UPDATE_INTERVAL = timedelta(seconds=60)
HUB_STATE_OFFLINE = 0
HUB_STATE_INITIALIZING = 1
HUB_STATE_ONLINE = 2
HUB_STATE_NAMES = {
    HUB_STATE_OFFLINE: "offline",
    HUB_STATE_INITIALIZING: "initializing",
    HUB_STATE_ONLINE: "online",
}

_LOGGER = logging.getLogger(__name__)


class LifeSmartHubCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Poll cloud status for all hubs in one config entry."""

    def __init__(self, hass, config_entry, client, hubs) -> None:
        """Initialize the hub coordinator."""
        self.client = client
        self.hub_ids = tuple(hub[HUB_ID_KEY] for hub in hubs)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="LifeSmart hub status",
            update_interval=HUB_STATUS_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch each hub independently so one offline hub does not hide the rest."""
        results = await asyncio.gather(
            *(self.client.get_hub_state_async(hub_id) for hub_id in self.hub_ids),
            return_exceptions=True,
        )
        data: dict[str, dict[str, Any]] = {}
        for hub_id, result in zip(self.hub_ids, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.debug("Unable to update LifeSmart hub %s: %s", hub_id, result)
                continue
            if isinstance(result, dict) and "state" in result:
                data[hub_id] = result
            else:
                _LOGGER.debug(
                    "LifeSmart returned an invalid status for hub %s: %s",
                    hub_id,
                    result,
                )
        return data


def get_hub_coordinator(
    hass, config_entry, runtime: LifeSmartRuntimeData
) -> LifeSmartHubCoordinator:
    """Return the shared hub coordinator for a config entry."""
    coordinator = runtime.hub_coordinator
    if not isinstance(coordinator, LifeSmartHubCoordinator):
        coordinator = LifeSmartHubCoordinator(
            hass, config_entry, runtime.client, runtime.hubs
        )
        runtime.hub_coordinator = coordinator
    return coordinator
