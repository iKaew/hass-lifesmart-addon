"""Reconcile device state after a LifeSmart transport reconnects."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
import logging

from .const import DEVICE_DATA_KEY, DEVICE_ID_KEY, DEVICE_TYPE_KEY, HUB_ID_KEY

_LOGGER = logging.getLogger(__name__)


async def async_apply_device_snapshot(runtime, devices, on_event) -> None:
    """Refresh existing device records and replay their channels as IO updates."""
    if not isinstance(devices, list):
        raise ValueError("LifeSmart device refresh returned an invalid response")

    known = {
        (device.get(HUB_ID_KEY), device.get(DEVICE_ID_KEY)): device
        for device in runtime.devices
    }
    availability = {key: False for key in runtime.device_availability}
    for device in devices:
        if not isinstance(device, dict):
            continue
        hub_id, device_id = device.get(HUB_ID_KEY), device.get(DEVICE_ID_KEY)
        if hub_id is None or device_id is None:
            continue
        key = (hub_id, device_id)
        availability[key] = device.get("stat", 1) == 1
        existing = known.get(key)
        if existing is None:
            # Entity discovery remains owned by config-entry setup.
            continue
        existing.update(deepcopy(device))
        device_type = existing.get(DEVICE_TYPE_KEY)
        channels = device.get(DEVICE_DATA_KEY, {})
        if not availability[key] or not device_type or not isinstance(channels, dict):
            continue
        # Thermostats interpret their mode relative to power. NATURE's P10
        # reports the effective fan speed, so apply it after the P9 setting.
        order = {"O": -2, "P1": -2, "MODE": -1, "P7": -1, "P10": 1}
        for channel in sorted(channels, key=lambda key: order.get(key, 0)):
            value = channels[channel]
            if not isinstance(value, dict) or not {"type", "val", "v"} & value.keys():
                continue
            on_event({
                "type": "io",
                "_snapshot": True,
                "msg": {
                    **value,
                    DEVICE_TYPE_KEY: device_type,
                    HUB_ID_KEY: hub_id,
                    DEVICE_ID_KEY: device_id,
                    "idx": channel,
                },
            })

    # dispatcher_send queues the entity handlers on this loop. Let them apply
    # the channel values before the caller publishes connection availability.
    await asyncio.sleep(0)
    for (hub_id, device_id), available in availability.items():
        runtime.set_device_available(hub_id, device_id, available)


class CloudStateRecovery:
    """Serialize cloud reconnection snapshots and live push updates on HA's loop."""

    def __init__(self, hass, runtime, on_event, close_socket) -> None:
        self.hass = hass
        self.runtime = runtime
        self.on_event = on_event
        self.close_socket = close_socket
        self._task = None
        self._pending = []
        self._generation = 0
        self._stopped = False

    def connected(self) -> None:
        """Start recovery after reconnection; initial setup already has a snapshot."""
        if self._stopped:
            return
        if self.runtime.last_error is None:
            self.runtime.set_connected(True)
            return
        self._invalidate()
        self._task = self.hass.async_create_task(
            self._recover(self._generation), "Refresh LifeSmart device state"
        )

    def disconnected(self, error) -> None:
        """Invalidate any snapshot still in flight when the transport disconnects."""
        self._invalidate()
        self.runtime.set_connected(False, error)

    def event(self, message) -> None:
        """Hold live updates until the older snapshot has been applied."""
        if self._stopped:
            return
        if self._task is not None:
            self._pending.append(message)
        else:
            self.on_event(message)

    def _invalidate(self) -> None:
        self._generation += 1
        if self._task is not None:
            self._task.cancel()
        self._task = None
        self._pending.clear()

    async def _recover(self, generation) -> None:
        try:
            devices = await self.runtime.client.get_all_device_async()
            if generation != self._generation:
                return
            await async_apply_device_snapshot(self.runtime, devices, self.on_event)
            while self._pending and generation == self._generation:
                pending, self._pending = self._pending, []
                for message in pending:
                    self.on_event(message)
                await asyncio.sleep(0)
            if generation == self._generation:
                self.runtime.set_connected(True)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            if generation == self._generation:
                self.runtime.set_connected(False, type(err).__name__)
                _LOGGER.warning("Unable to refresh LifeSmart device state: %s", type(err).__name__)
                # Re-enter the existing websocket reconnect/backoff path.
                await self.hass.async_add_executor_job(self.close_socket)
        finally:
            if generation == self._generation:
                self._task = None
                self._pending.clear()

    async def async_close(self) -> None:
        """Cancel recovery before unloading the config entry."""
        self._stopped = True
        task = self._task
        self._invalidate()
        if task is not None:
            with suppress(asyncio.CancelledError):
                await task
