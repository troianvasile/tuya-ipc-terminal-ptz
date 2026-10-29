"""Admin-only HA websocket proxy for private Tuya bridge management.

No bridge credentials or raw Tuya QR token are returned to browser JavaScript.
"""
from __future__ import annotations

import asyncio
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.helpers import entity_registry as er

from .const import CONF_BROWSER_URL, DOMAIN, CONF_URL, CONF_USERNAME, CONF_PASSWORD


def bridge_request(data: dict, method: str, path: str, fields: dict | None = None,
                   binary: bool = False):
    credentials = (data[CONF_USERNAME] + ":" + data[CONF_PASSWORD]).encode()
    headers = {"Authorization": "Basic " + base64.b64encode(credentials).decode()}
    payload = None
    if fields is not None:
        if path == "/api/ptz/move":
            payload = json.dumps(fields).encode()
            headers["Content-Type"] = "application/json"
        else:
            payload = urlencode(fields).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(data[CONF_URL].rstrip("/") + path, data=payload,
                  method=method, headers=headers)
    with urlopen(req, timeout=12) as response:
        body = response.read(65536)
        return base64.b64encode(body).decode() if binary else json.loads(body)


def _data(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ValueError("Unknown bridge")
    return entry.data


def _entry(hass, entry_id: str | None):
    """Return the requested bridge entry, or the only configured bridge."""
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return entry
    else:
        entries = hass.config_entries.async_entries(DOMAIN)
        if len(entries) == 1:
            return entries[0]
    raise ValueError("Unknown bridge")


def _admin(connection, msg):
    if connection.user is None or not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Admin permission required")
        return False
    return True


@websocket_api.websocket_command({
    vol.Required("type"): "tuya_ipc_bridge/manage",
    vol.Optional("entry_id"): str,
    vol.Required("action"): vol.In(("status", "cameras", "dashboard", "qr_start", "qr_status", "qr_image", "ptz_move")),
    vol.Optional("region"): str,
    vol.Optional("email"): str,
    vol.Optional("job_id"): str,
    vol.Optional("camera"): str,
    vol.Optional("direction"): str,
    vol.Optional("duration_ms"): int,
})
@websocket_api.async_response
async def ws_manage(hass, connection, msg):
    if not _admin(connection, msg):
        return
    action = msg["action"]
    try:
        entry = _entry(hass, msg.get("entry_id"))
        data = entry.data
        if action == "qr_start":
            if not msg.get("region") or not msg.get("email"):
                raise ValueError("Missing region/email")
            method, path, fields, binary = "POST", "/api/qr", {
                "region": msg["region"], "email": msg["email"],
            }, False
        elif action in ("qr_status", "qr_image"):
            jid = msg.get("job_id", "")
            if len(jid) != 32 or any(ch not in "0123456789abcdef" for ch in jid):
                raise ValueError("Invalid QR job")
            method, path, fields, binary = "GET", (
                "/api/qr/" + jid + ("/image" if action == "qr_image" else "/status")
            ), None, action == "qr_image"
        elif action == "ptz_move":
            if not msg.get("camera") or not msg.get("direction"):
                raise ValueError("Missing PTZ camera or direction")
            method, path, fields, binary = "POST", "/api/ptz/move", {
                "camera": msg["camera"], "direction": msg["direction"],
                "duration_ms": msg.get("duration_ms", 400),
            }, False
        elif action == "dashboard":
            method, path, fields, binary = "GET", "/api/cameras", None, False
        else:
            method, path, fields, binary = "GET", (
                "/api/cameras" if action == "cameras" else "/api/health"
            ), None, False
        result = await asyncio.wait_for(
            hass.async_add_executor_job(bridge_request, data, method, path, fields, binary),
            timeout=15,
        )
        if action == "status":
            result["manager_url"] = data.get(CONF_BROWSER_URL) or data[CONF_URL]
        elif action == "dashboard":
            camera_response = result
            registry = er.async_get(hass)
            result = {
                "entry_id": entry.entry_id,
                "manager_url": data.get(CONF_BROWSER_URL) or data[CONF_URL],
                "cameras": [
                    {
                        "name": camera.get("name", "Tuya camera"),
                        "camera_id": camera.get("device_id"),
                        "entity_id": registry.async_get_entity_id(
                            "camera", DOMAIN,
                            f"{entry.entry_id}_{camera.get('device_id', '')}",
                        ),
                    }
                    for camera in camera_response.get("cameras", [])
                    if isinstance(camera, dict) and isinstance(camera.get("device_id"), str)
                ],
            }
        connection.send_result(msg["id"], {"image": result} if binary else result)
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError, asyncio.TimeoutError):
        connection.send_error(msg["id"], "bridge_error", "Bridge request failed; check connection or login")
