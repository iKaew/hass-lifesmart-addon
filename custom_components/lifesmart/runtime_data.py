"""Runtime state for a LifeSmart config entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from weakref import WeakSet

from .const import DEVICE_ID_KEY, HUB_ID_KEY


@dataclass(slots=True)
class LifeSmartRuntimeData:
    """Objects and state owned by one LifeSmart config entry."""

    client: Any
    devices: list[dict[str, Any]]
    hubs: list[dict[str, Any]] = field(default_factory=list)
    scenes: list[dict[str, Any]] = field(default_factory=list)
    hub_coordinator: Any | None = None
    exclude_devices: list[str] = field(default_factory=list)
    exclude_hubs: list[str] = field(default_factory=list)
    ai_include_hubs: list[str] = field(default_factory=list)
    ai_include_items: list[str] = field(default_factory=list)
    state_manager: Any | None = None
    update_listener: Callable[[], None] | None = None
    connected: bool = False
    last_error: str | None = None
    device_availability: dict[tuple[str, str], bool] = field(default_factory=dict)
    entities: WeakSet = field(default_factory=WeakSet)

    def track_entities(self, entities) -> None:
        """Associate entities with this entry's connection state."""
        for entity in entities:
            entity._lifesmart_runtime = self
            raw_device = getattr(entity, "_raw_device_data", {})
            hub_id = getattr(
                entity,
                "hub_id",
                getattr(entity, "_hub_id", raw_device.get(HUB_ID_KEY)),
            )
            device_id = getattr(
                entity,
                "device_id",
                getattr(entity, "_device_id", raw_device.get(DEVICE_ID_KEY)),
            )
            if hub_id is not None and device_id is not None:
                entity._lifesmart_device_key = (hub_id, device_id)
            self.entities.add(entity)

    def set_connected(self, connected: bool, error: str | None = None) -> None:
        """Update connection state and refresh all loaded entities."""
        if self.connected == connected and self.last_error == error:
            return
        self.connected = connected
        self.last_error = error
        for entity in tuple(self.entities):
            # The websocket can connect while platforms are still adding their
            # entities. An entity without hass has no event loop to schedule on;
            # once added, it reads the current availability from this runtime.
            if getattr(entity, "hass", None) is None:
                continue
            entity.schedule_update_ha_state()

    def set_device_available(
        self, hub_id: str, device_id: str, available: bool
    ) -> None:
        """Update availability for every entity belonging to one device."""
        device_key = (hub_id, device_id)
        if self.device_availability.get(device_key) == available:
            return
        self.device_availability[device_key] = available
        for entity in tuple(self.entities):
            if getattr(entity, "_lifesmart_device_key", None) != device_key:
                continue
            if getattr(entity, "hass", None) is None:
                continue
            entity.schedule_update_ha_state()

    def set_hub_devices_unavailable(self, hub_id: str) -> None:
        """Mark every known child device of an offline hub unavailable."""
        for device_hub_id, device_id in tuple(self.device_availability):
            if device_hub_id == hub_id:
                self.set_device_available(device_hub_id, device_id, False)


class LifeSmartAvailabilityMixin:
    """Expose the shared websocket connection as entity availability."""

    _lifesmart_runtime: LifeSmartRuntimeData | None = None
    _lifesmart_device_key: tuple[str, str] | None = None

    @property
    def available(self) -> bool:
        """Return whether the LifeSmart websocket is connected."""
        runtime = self._lifesmart_runtime
        if runtime is None:
            return True
        if not runtime.connected:
            return False
        device_key = self._lifesmart_device_key
        if device_key is None:
            return True
        return runtime.device_availability.get(device_key, True)


def get_runtime_data(hass, entry) -> LifeSmartRuntimeData:
    """Return typed runtime data, with a compatibility path for test doubles."""
    runtime_data = getattr(entry, "runtime_data", None)
    if isinstance(runtime_data, LifeSmartRuntimeData):
        return runtime_data

    # Some lightweight platform tests use config-entry doubles without
    # runtime_data. Keep that test seam out of production setup paths.
    from .const import DOMAIN

    legacy = hass.data[DOMAIN][entry.entry_id]
    return LifeSmartRuntimeData(
        client=legacy.get("client"),
        devices=legacy["devices"],
        hubs=legacy.get("hubs", []),
        scenes=legacy.get("scenes", []),
        hub_coordinator=legacy.get("hub_coordinator"),
        exclude_devices=legacy.get("exclude_devices", []),
        exclude_hubs=legacy.get("exclude_hubs", []),
        ai_include_hubs=legacy.get("ai_include_hubs", []),
        ai_include_items=legacy.get("ai_include_items", []),
        state_manager=legacy.get("state_manager"),
        update_listener=legacy.get("update_listener"),
        device_availability=legacy.get("device_availability", {}),
    )
