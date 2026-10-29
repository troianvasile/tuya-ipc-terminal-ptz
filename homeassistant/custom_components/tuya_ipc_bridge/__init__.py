"""Tuya IPC Bridge: standalone bridge status in Home Assistant."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api
from .management import ws_manage
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .coordinator import BridgeCoordinator
from .talkback import async_register as async_register_talkback


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
        websocket_api.async_register_command(hass, ws_manage)
    async_register_talkback(hass)
    coordinator = BridgeCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
    await coordinator.async_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "camera"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "camera"])
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
