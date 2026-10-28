"""Setup standalone bridge from Home Assistant, without Supervisor."""
from __future__ import annotations

import asyncio
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, DOMAIN

SCHEMA = vol.Schema({
    vol.Required(CONF_URL, default="http://127.0.0.1:8788"): str,
    vol.Required(CONF_USERNAME, default="admin"): str,
    vol.Required(CONF_PASSWORD): str,
})


def check_bridge(url: str, username: str, password: str) -> None:
    """Verify the private management endpoint with bounded synchronous I/O."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid bridge URL")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Use a base URL without path, query or fragment")
    if len(password) < 20:
        raise ValueError("Bridge password must be at least 20 characters")
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    req = Request(url.rstrip("/") + "/api/health",
                  headers={"Authorization": "Basic " + auth})
    with urlopen(req, timeout=6) as response:
        payload = json.loads(response.read(4096))
    if payload.get("service") != "tuya-ipc-bridge":
        raise ValueError("Not a Tuya IPC Bridge management endpoint")


class TuyaIPCBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Interactive setup of a separately running bridge."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            try:
                await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        check_bridge, url,
                        user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    ), timeout=8
                )
            except (HTTPError, URLError, ValueError, OSError, asyncio.TimeoutError, json.JSONDecodeError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Tuya IPC Bridge", data={**user_input, CONF_URL: url}
                )
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)
