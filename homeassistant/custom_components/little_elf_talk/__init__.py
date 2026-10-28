"""Little Elf browser microphone -> authenticated HA WebSocket -> RTSP PCMU.

Portable, YAML-configured prototype. Not an official Tuya or HA integration.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .rtsp_audio import RtspPcmuBackchannel, RtspError

DOMAIN = "little_elf_talk"
_LOGGER = logging.getLogger(__name__)
MAX_SESSIONS = 4
SILENCE_TIMEOUT = 5.0

CAMERA_SCHEMA = vol.Schema({
    vol.Required("rtsp_url"): cv.string,
})
CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): vol.Schema({
        vol.Required("cameras"): {vol.Match(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"): CAMERA_SCHEMA},
        vol.Optional("admin_only", default=True): cv.boolean,
    })
}, extra=vol.ALLOW_EXTRA)


@dataclass
class Session:
    """Session is owned by exactly one HA WebSocket connection."""

    token: str
    camera: str
    owner: Any
    start_message_id: int
    rtsp: RtspPcmuBackchannel
    last_audio: float


def _state(hass: HomeAssistant) -> dict[str, Any]:
    return hass.data[DOMAIN]


def _authorised(hass: HomeAssistant, connection: Any) -> bool:
    state = _state(hass)
    user = connection.user
    return bool(user) and (not state["admin_only"] or user.is_admin)


async def _end_session(hass: HomeAssistant, token: str) -> None:
    state = _state(hass)
    sess = state["sessions"].pop(token, None)
    if not sess:
        return
    sess.owner.subscriptions.pop(sess.start_message_id, None)
    try:
        await sess.rtsp.close()
    except Exception:
        _LOGGER.exception("Failed to close Little Elf talkback session")


async def _watchdog(hass: HomeAssistant) -> None:
    try:
        while True:
            await asyncio.sleep(1)
            now = time.monotonic()
            state = _state(hass)
            for token, sess in list(state["sessions"].items()):
                if now - sess.last_audio > SILENCE_TIMEOUT:
                    await _end_session(hass, token)
    except asyncio.CancelledError:
        pass


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/start",
    vol.Required("camera"): cv.string,
})
@websocket_api.async_response
async def ws_start(hass: HomeAssistant, connection: Any, msg: dict) -> None:
    """Create a new, independently authorised RTSP talkback session."""
    state = _state(hass)
    if not _authorised(hass, connection):
        connection.send_error(msg["id"], "unauthorized", "Administrator access required")
        return
    camera = msg["camera"]
    camera_config = state["cameras"].get(camera)
    if camera_config is None:
        connection.send_error(msg["id"], "not_found", "Unknown camera")
        return
    if len(state["sessions"]) >= MAX_SESSIONS:
        connection.send_error(msg["id"], "busy", "Too many active talkback sessions")
        return
    if any(s.camera == camera for s in state["sessions"].values()):
        connection.send_error(msg["id"], "busy", "Camera microphone is already in use")
        return

    # Reserve camera *before* awaiting RTSP setup to avoid simultaneous starts.
    token = secrets.token_urlsafe(24)
    # A pending reservation guards overlapping starts; it is removed on failure.
    if camera in state["starting"]:
        connection.send_error(msg["id"], "busy", "Camera microphone is starting")
        return
    state["starting"].add(camera)
    rtsp = RtspPcmuBackchannel(camera_config["rtsp_url"])
    try:
        await asyncio.wait_for(rtsp.start(), timeout=18)
    except (RtspError, OSError, asyncio.TimeoutError, ValueError) as err:
        await rtsp.close()
        _LOGGER.warning("Talkback setup failed for %s: %s", camera, err)
        connection.send_error(msg["id"], "unavailable", "RTSP talkback setup failed")
        return
    finally:
        state["starting"].discard(camera)

    sess = Session(
        token=token, camera=camera, owner=connection,
        start_message_id=msg["id"], rtsp=rtsp,
        last_audio=time.monotonic(),
    )
    state["sessions"][token] = sess

    # A WebSocket drop un-subscribes; this makes cleanup independent of any
    # frontend stop event (mobile app killed, network loss, browser crash).
    @callback
    def on_disconnect() -> None:
        hass.async_create_task(_end_session(hass, token))

    connection.subscriptions[msg["id"]] = on_disconnect
    connection.send_result(msg["id"], {"session": token})


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/chunk",
    vol.Required("session"): cv.string,
    vol.Required("audio"): cv.string,
})
@websocket_api.async_response
async def ws_chunk(hass: HomeAssistant, connection: Any, msg: dict) -> None:
    """Accept one bounded base64-encoded 8 kHz mono PCMU RTP payload."""
    sess: Session | None = _state(hass)["sessions"].get(msg["session"])
    if sess is None or sess.owner is not connection:
        connection.send_error(msg["id"], "not_found", "Talkback session not found")
        return
    text = msg["audio"]
    if len(text) > 900:
        connection.send_error(msg["id"], "invalid_format", "Audio packet too large")
        return
    try:
        samples = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        connection.send_error(msg["id"], "invalid_format", "Invalid base64 audio")
        return
    if not 1 <= len(samples) <= 640:
        connection.send_error(msg["id"], "invalid_format", "Expected PCMU samples")
        return
    try:
        await sess.rtsp.write_pcmu(samples)
        sess.last_audio = time.monotonic()
    except (RtspError, OSError, asyncio.TimeoutError, ValueError) as err:
        _LOGGER.warning("Talkback forwarding failed for %s: %s", sess.camera, err)
        await _end_session(hass, sess.token)
        connection.send_error(msg["id"], "unavailable", "RTSP backchannel disconnected")
        return
    connection.send_result(msg["id"])


# Compatibility with the original working Home Assistant prototype:
# older cards send {type:little_elf_talk/audio, camera, session, pcmu}.
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/audio",
    vol.Required("camera"): cv.string,
    vol.Required("session"): cv.string,
    vol.Required("pcmu"): cv.string,
})
@websocket_api.async_response
async def ws_audio(hass: HomeAssistant, connection: Any, msg: dict) -> None:
    sess: Session | None = _state(hass)["sessions"].get(msg["session"])
    if sess is None or sess.camera != msg["camera"] or sess.owner is not connection:
        connection.send_error(msg["id"], "not_found", "Talkback session not found")
        return
    await ws_chunk(
        hass, connection,
        {"id": msg["id"], "session": msg["session"], "audio": msg["pcmu"]},
    )


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/stop",
    vol.Required("session"): cv.string,
    vol.Optional("camera"): cv.string,
})
@websocket_api.async_response
async def ws_stop(hass: HomeAssistant, connection: Any, msg: dict) -> None:
    """Release the sender. A repeated stop is harmless."""
    sess: Session | None = _state(hass)["sessions"].get(msg["session"])
    if sess is not None and sess.owner is not connection:
        connection.send_error(msg["id"], "unauthorized", "Session belongs to another user")
        return
    if sess:
        await _end_session(hass, sess.token)
    connection.send_result(msg["id"])


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Load the YAML camera allowlist and register authenticated commands."""
    options = config.get(DOMAIN)
    if options is None:
        return True
    hass.data[DOMAIN] = {
        "cameras": options["cameras"],
        "admin_only": options["admin_only"],
        "sessions": {},
        "starting": set(),
    }
    websocket_api.async_register_command(hass, ws_start)
    websocket_api.async_register_command(hass, ws_chunk)
    websocket_api.async_register_command(hass, ws_audio)
    websocket_api.async_register_command(hass, ws_stop)
    task = hass.async_create_task(_watchdog(hass))

    @callback
    def on_shutdown(_event: Any) -> None:
        task.cancel()
        for token in list(_state(hass)["sessions"]):
            hass.async_create_task(_end_session(hass, token))

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_shutdown)
    return True
