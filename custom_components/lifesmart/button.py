"""Support for LifeSmart hub buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, HUB_ID_KEY
from .hub import HUB_STATE_ONLINE, get_hub_coordinator
from .runtime_data import get_runtime_data


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up restart buttons for discovered LifeSmart hubs."""
    runtime = get_runtime_data(hass, config_entry)
    if not runtime.hubs:
        return

    coordinator = get_hub_coordinator(hass, config_entry, runtime)
    async_add_entities(
        LifeSmartHubRestartButton(coordinator, runtime.client, hub)
        for hub in runtime.hubs
    )


class LifeSmartHubRestartButton(CoordinatorEntity, ButtonEntity):
    """Restart a LifeSmart hub through the cloud API."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_translation_key = "restart_hub"

    def __init__(self, coordinator, client, hub) -> None:
        """Initialize a hub restart button."""
        super().__init__(coordinator)
        self._client = client
        self._hub_id = hub[HUB_ID_KEY]
        self._attr_unique_id = f"{self._hub_id}_restart"

    @property
    def available(self) -> bool:
        """Only offer restart while the hub reports that it is online."""
        state = (self.coordinator.data or {}).get(self._hub_id, {}).get("state")
        return super().available and state == HUB_STATE_ONLINE

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the button to its hub device."""
        return DeviceInfo(identifiers={(DOMAIN, self._hub_id)})

    async def async_press(self) -> None:
        """Restart the hub."""
        try:
            response = await self._client.reboot_hub_async(self._hub_id)
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="hub_restart_failed",
            ) from err

        if not isinstance(response, dict) or response.get("code") != 0:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="hub_restart_rejected",
            )
