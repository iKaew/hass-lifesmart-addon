"""Bridge native climate temperatures to Home Assistant releases before 2026.11."""

from homeassistant.components.climate import ClimateEntity


class LifeSmartClimateEntity(ClimateEntity):
    """Use the native API without declaring deprecated members on newer cores."""

    if not hasattr(ClimateEntity, "native_temperature_unit"):
        _attr_native_temperature_unit: str
        _attr_native_current_temperature: float | None = None
        _attr_native_target_temperature: float | None = None

        @property
        def native_temperature_unit(self) -> str:
            """Return the device's temperature unit."""
            return self._attr_native_temperature_unit

        @property
        def native_current_temperature(self) -> float | None:
            """Return the current temperature in the device's unit."""
            return self._attr_native_current_temperature

        @property
        def native_target_temperature(self) -> float | None:
            """Return the target temperature in the device's unit."""
            return self._attr_native_target_temperature

        @property
        def temperature_unit(self) -> str:
            """Expose the native unit to older cores."""
            return self.native_temperature_unit

        @property
        def current_temperature(self) -> float | None:
            """Expose the native current temperature to older cores."""
            return self.native_current_temperature

        @property
        def target_temperature(self) -> float | None:
            """Expose the native target temperature to older cores."""
            return self.native_target_temperature
