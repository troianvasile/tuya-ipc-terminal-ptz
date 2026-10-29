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

from .const import CONF_BROWSER_URL, CONF_PASSWORD, CONF_URL, CONF_USERNAME, DOMAIN


def schema(defaults: dict | None = None) -> vol.Schema:
    """Build a config schema with defaults for setup or reconfiguration."""
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_URL, default=defaults.get(CONF_URL, "http://127.0.0.1:8788")): str,
        vol.Required(CONF_BROWSER_URL, default=defaults.get(CONF_BROWSER_URL, "")): str,
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "admin")): str,
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


def normalize_browser_url(url: str) -> str:
    """Validate an optional browser-facing manager URL without credentials."""
    url = url.rstrip("/")
    if not url:
        return ""
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment):
        raise ValueError("Invalid browser URL")
    return url


class TuyaIPCBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Interactive setup of a separately running bridge."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            try:
                browser_url = normalize_browser_url(user_input[CONF_BROWSER_URL])
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
                    title="Tuya IPC Bridge",
                    data={**user_input, CONF_URL: url, CONF_BROWSER_URL: browser_url},
                )
        return self.async_show_form(step_id="user", data_schema=schema(), errors=errors)

    async def async_step_reconfigure(self, user_input: dict | None = None) -> FlowResult:
        """Allow changing an expired password or browser-facing manager URL."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            try:
                browser_url = normalize_browser_url(user_input[CONF_BROWSER_URL])
                await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        check_bridge, url,
                        user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    ), timeout=8
                )
            except (HTTPError, URLError, ValueError, OSError, asyncio.TimeoutError, json.JSONDecodeError):
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**user_input, CONF_URL: url, CONF_BROWSER_URL: browser_url},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema(entry.data), errors=errors
        )
