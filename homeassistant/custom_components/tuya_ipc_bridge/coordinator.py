"""Shared refresh coordinator for a Tuya IPC Bridge entry."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import fetch_cameras, fetch_health

_LOGGER = logging.getLogger(__name__)


class BridgeCoordinator(DataUpdateCoordinator[dict]):
    """Refresh bridge health and discovered cameras together."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Tuya IPC Bridge {entry.title}",
            update_interval=timedelta(seconds=60),
        )
        self.entry = entry

    async def _async_update_data(self) -> dict:
        try:
            health, cameras = await self.hass.async_add_executor_job(
                lambda: (fetch_health(self.entry.data), fetch_cameras(self.entry.data))
            )
        except Exception as exc:
            raise UpdateFailed("Cannot reach Tuya bridge") from exc
        return {"health": health, "cameras": cameras}
