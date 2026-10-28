"""Expose standalone bridge availability and account count."""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import timedelta
from urllib.request import Request, urlopen

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_PASSWORD, CONF_URL, CONF_USERNAME


def fetch_health(data: dict) -> dict:
    auth = base64.b64encode(
        (data[CONF_USERNAME] + ":" + data[CONF_PASSWORD]).encode()
    ).decode()
    req = Request(data[CONF_URL].rstrip("/") + "/api/health",
                  headers={"Authorization": "Basic " + auth})
    with urlopen(req, timeout=7) as response:
        payload = json.loads(response.read(4096))
    if payload.get("service") != "tuya-ipc-bridge":
        raise ValueError("Unexpected bridge response")
    return payload


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    async def refresh():
        try:
            return await asyncio.wait_for(
                hass.async_add_executor_job(fetch_health, entry.data), timeout=10
            )
        except Exception as exc:
            raise UpdateFailed("Cannot reach Tuya bridge") from exc

    coordinator = DataUpdateCoordinator(
        hass, logger=__import__("logging").getLogger(__name__),
        name="Tuya bridge status", update_method=refresh,
        update_interval=timedelta(seconds=60),
    )
    await coordinator.async_refresh()
    async_add_entities([
        BridgeSensor(coordinator, entry, "account_count", "Accounts"),
        BridgeSensor(coordinator, entry, "rtsp", "RTSP status"),
    ])


class BridgeSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name):
        self.coordinator = coordinator
        self.key = key
        self._attr_name = name
        self._attr_unique_id = entry.entry_id + "_" + key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="Tuya IPC Bridge"
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self.key) if self.coordinator.data else None

    @property
    def available(self):
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
