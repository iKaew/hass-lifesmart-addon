"""Support LifeSmart SPOT devices as Home Assistant infrared emitters."""

from __future__ import annotations

from typing import Any

from homeassistant.components.infrared import InfraredCommand, InfraredEmitterEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from . import device_identifier, device_via_info
from .const import (
    DOMAIN as DOMAIN,
    DEVICE_ID_KEY,
    DEVICE_NAME_KEY,
    DEVICE_TYPE_KEY,
    DEVICE_VERSION_KEY,
    HUB_ID_KEY,
    SPOT_TYPES,
)
from .runtime_data import LifeSmartAvailabilityMixin, get_runtime_data

# Pronto represents durations in carrier periods and derives the carrier from a
# 0.241246 microsecond clock. LifeSmart SendCodes accepts this raw IR form.
PRONTO_CLOCK_US = 0.241246


async def async_setup_entry(
    hass: HomeAssistant, config_entry, async_add_entities
) -> None:
    """Set up LifeSmart infrared emitter entities."""
    runtime = get_runtime_data(hass, config_entry)
    client = runtime.client
    excluded_devices = runtime.exclude_devices
    excluded_hubs = runtime.exclude_hubs

    entities = [
        LifeSmartInfraredEmitter(device, client)
        for device in runtime.devices
        if device[DEVICE_TYPE_KEY] in SPOT_TYPES
        and device[DEVICE_ID_KEY] not in excluded_devices
        and device[HUB_ID_KEY] not in excluded_hubs
    ]
    runtime.track_entities(entities)
    async_add_entities(entities)


class LifeSmartInfraredEmitter(LifeSmartAvailabilityMixin, InfraredEmitterEntity):
    """A LifeSmart SPOT-family infrared emitter."""

    _attr_has_entity_name = True
    _attr_name = "Infrared"

    def __init__(self, raw_device_data: dict[str, Any], client: Any) -> None:
        """Initialize the emitter."""
        self._client = client
        self._raw_device_data = raw_device_data
        self._device_id = raw_device_data[DEVICE_ID_KEY]
        self._hub_id = raw_device_data[HUB_ID_KEY]
        self._device_type = raw_device_data[DEVICE_TYPE_KEY]
        self._device_name = raw_device_data[DEVICE_NAME_KEY]
        self._sw_version = raw_device_data.get(DEVICE_VERSION_KEY, "")

        self._attr_unique_id = (
            f"{self._device_type}_{self._hub_id}_{self._device_id}_infrared"
        ).lower()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device registry information."""
        return DeviceInfo(
            identifiers={device_identifier(self._hub_id, self._device_id)},
            name=self._device_name,
            manufacturer="LifeSmart",
            model=self._device_type,
            sw_version=self._sw_version,
            **device_via_info(self._raw_device_data, self._hub_id),
        )

    async def async_send_command(self, command: InfraredCommand) -> None:
        """Transmit a Home Assistant IR command through LifeSmart SendCodes."""
        try:
            pronto_code = command_to_pronto(command)
            response = await self._client.send_ir_code_async(
                self._hub_id, self._device_id, pronto_code
            )
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(
                f"Invalid infrared command for {self._device_name}: {err}"
            ) from err
        except Exception as err:
            raise HomeAssistantError(
                f"Unable to send infrared command through {self._device_name}"
            ) from err

        if isinstance(response, dict) and response.get("code") not in (None, 0):
            raise HomeAssistantError(
                f"LifeSmart rejected the infrared command: {response.get('message', response)}"
            )


def command_to_pronto(command: InfraredCommand) -> str:
    """Convert a protocol-neutral Home Assistant command to raw Pronto hex."""
    modulation = getattr(command, "modulation", None)
    if not isinstance(modulation, int) or modulation <= 0:
        raise ValueError("a positive carrier frequency is required")

    raw_timings = command.get_raw_timings()
    if not raw_timings:
        raise ValueError("the command contains no timings")

    frequency_word = round(1_000_000 / (modulation * PRONTO_CLOCK_US))
    if not 1 <= frequency_word <= 0xFFFF:
        raise ValueError(f"unsupported carrier frequency: {modulation} Hz")

    period_us = frequency_word * PRONTO_CLOCK_US
    durations: list[int] = []
    for timing_us in _normalize_raw_timings(raw_timings):
        durations.append(max(1, round(timing_us / period_us)))

    if len(durations) // 2 > 0xFFFF:
        raise ValueError("the command contains too many timing pairs")

    words = [0, frequency_word, len(durations) // 2, 0, *durations]
    if any(word > 0xFFFF for word in words):
        raise ValueError("a timing exceeds the Pronto format limit")
    return " ".join(f"{word:04X}" for word in words)


def _normalize_raw_timings(raw_timings: list[Any]) -> list[int]:
    """Return alternating positive mark/space durations from an IR command."""
    timings: list[int] = []
    for index, timing in enumerate(raw_timings):
        if isinstance(timing, int):
            expected_positive = index % 2 == 0
            if timing == 0 or (timing > 0) != expected_positive:
                raise ValueError("timings must alternate positive marks and negative spaces")
            timings.append(abs(timing))
            continue

        # Compatibility with the paired Timing objects used by early versions
        # of infrared-protocols.
        high_us = getattr(timing, "high_us", None)
        low_us = getattr(timing, "low_us", None)
        if not isinstance(high_us, int) or not isinstance(low_us, int):
            raise TypeError("timings must be integers or high/low timing pairs")
        if high_us <= 0 or low_us < 0:
            raise ValueError("timings must have a positive high and non-negative low")
        timings.extend((high_us, low_us))

    # Protocol encoders normally finish with a mark. Pronto requires complete
    # mark/space pairs, so supply the shortest representable trailing space.
    if len(timings) % 2:
        timings.append(1)
    return timings
