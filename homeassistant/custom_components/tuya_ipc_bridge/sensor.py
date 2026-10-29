"""Expose standalone bridge availability and account count."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry

from .const import CONF_BROWSER_URL, CONF_URL, DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
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
            identifiers={(DOMAIN, entry.entry_id)},
            name="Tuya IPC Bridge",
            configuration_url=entry.data.get(CONF_BROWSER_URL) or entry.data[CONF_URL],
        )

    @property
    def native_value(self):
        health = self.coordinator.data.get("health", {}) if self.coordinator.data else {}
        return health.get(self.key) if isinstance(health, dict) else None

    @property
    def available(self):
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
