"""Support for LifeSmart scenes."""

from __future__ import annotations

from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, HUB_ID_KEY
from .runtime_data import get_runtime_data


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up scenes discovered from the LifeSmart cloud API."""
    runtime = get_runtime_data(hass, config_entry)
    async_add_entities(
        LifeSmartScene(runtime.client, scene) for scene in runtime.scenes
    )


class LifeSmartScene(Scene):
    """A stateless scene executed by a LifeSmart hub."""

    def __init__(self, client, scene: dict[str, Any]) -> None:
        """Initialize a LifeSmart scene."""
        self._client = client
        self._hub_id = scene[HUB_ID_KEY]
        self._scene_id = scene["id"]
        self._attr_name = scene["name"]
        self._attr_unique_id = f"{self._hub_id}_{self._scene_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the scene to the hub which executes it."""
        return DeviceInfo(identifiers={(DOMAIN, self._hub_id)})

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the scene through the LifeSmart cloud API."""
        try:
            response = await self._client.set_scene_async(self._hub_id, self._scene_id)
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="scene_activation_failed",
            ) from err

        if isinstance(response, int):
            accepted = response == 0
        else:
            accepted = isinstance(response, dict) and response.get("code") in (
                0,
                "success",
            )
        if not accepted:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="scene_activation_rejected",
            )
