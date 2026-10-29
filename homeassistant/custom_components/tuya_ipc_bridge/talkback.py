"""Admin-only browser microphone sessions for discovered bridge cameras."""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .camera import get_camera_rtsp_url
from .const import DOMAIN
from .rtsp_audio import RtspError, RtspPcmuBackchannel

_LOGGER = logging.getLogger(__name__)
_STATE = "talkback"
_MAX_SESSIONS = 4
_SILENCE_TIMEOUT = 5.0


@dataclass
class TalkbackSession:
    """One browser-owned RTSP audio-backchannel session."""

    token: str
    entry_id: str
    camera_id: str
    owner: Any
    start_message_id: int
    rtsp: RtspPcmuBackchannel
    last_audio: float
    started_at: float
    packet_count: int = 0
    audio_queue: asyncio.Queue[bytes] = field(
        default_factory=lambda: asyncio.Queue(maxsize=12)
    )
    sender_task: asyncio.Task[None] | None = None


def _state(hass: HomeAssistant) -> dict[str, Any]:
    return hass.data[DOMAIN][_STATE]


def _admin(connection: Any) -> bool:
    return bool(connection.user) and connection.user.is_admin


async def _end_session(hass: HomeAssistant, token: str) -> None:
    session = _state(hass)["sessions"].pop(token, None)
    if session is None:
        return
    session.owner.subscriptions.pop(session.start_message_id, None)
    if session.sender_task and session.sender_task is not asyncio.current_task():
        session.sender_task.cancel()
        await asyncio.gather(session.sender_task, return_exceptions=True)
    try:
        await session.rtsp.close()
    except (OSError, asyncio.TimeoutError, ValueError):
        _LOGGER.warning("Could not close talkback session")


async def _send_audio(hass: HomeAssistant, session: TalkbackSession) -> None:
    try:
        while True:
            audio = await session.audio_queue.get()
            await session.rtsp.write_pcmu(audio)
    except asyncio.CancelledError:
        raise
    except (RtspError, OSError, asyncio.TimeoutError, ValueError):
        _LOGGER.warning("Talkback RTSP backchannel disconnected")
        await _end_session(hass, session.token)


async def _watchdog(hass: HomeAssistant) -> None:
    try:
        while True:
            await asyncio.sleep(1)
            now = time.monotonic()
            for token, session in list(_state(hass)["sessions"].items()):
                if now - session.last_audio > _SILENCE_TIMEOUT:
                    await _end_session(hass, token)
    except asyncio.CancelledError:
        return


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/ptt_start",
    vol.Required("entry_id"): cv.string,
    vol.Required("camera_id"): cv.string,
})
@websocket_api.async_response
async def ws_start(hass: HomeAssistant, connection: Any, msg: dict) -> None:
    """Start a bounded microphone session for a discovered camera."""
    if not _admin(connection):
        connection.send_error(msg["id"], "unauthorized", "Administrator access required")
        return
    state = _state(hass)
    if len(state["sessions"]) >= _MAX_SESSIONS:
        connection.send_error(msg["id"], "busy", "Too many active talkback sessions")
        return
    key = (msg["entry_id"], msg["camera_id"])
    if key in state["starting"] or any(
        (session.entry_id, session.camera_id) == key
        for session in state["sessions"].values()
    ):
        connection.send_error(msg["id"], "busy", "Camera microphone is already in use")
        return
    coordinator = hass.data[DOMAIN].get(msg["entry_id"], {}).get("coordinator")
    source = get_camera_rtsp_url(coordinator, msg["camera_id"])
    if source is None:
        connection.send_error(msg["id"], "not_found", "Unknown or unavailable camera")
        return
    state["starting"].add(key)
    rtsp = RtspPcmuBackchannel(source)
    try:
        await asyncio.wait_for(rtsp.start(), timeout=18)
    except (RtspError, OSError, asyncio.TimeoutError, ValueError) as err:
        await rtsp.close()
        _LOGGER.warning("Talkback setup failed: %s", err)
        connection.send_error(msg["id"], "unavailable", "RTSP talkback setup failed")
        return
    finally:
        state["starting"].discard(key)
    token = secrets.token_urlsafe(24)
    started_at = time.monotonic()
    session = TalkbackSession(
        token, msg["entry_id"], msg["camera_id"], connection, msg["id"], rtsp,
        started_at, started_at,
    )
    state["sessions"][token] = session
    session.sender_task = hass.async_create_background_task(
        _send_audio(hass, session), f"{DOMAIN}_talkback_sender"
    )

    @callback
    def on_disconnect() -> None:
        hass.async_create_task(_end_session(hass, token))

    connection.subscriptions[msg["id"]] = on_disconnect
    connection.send_result(msg["id"], {"session": token})


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/ptt_chunk",
    vol.Required("session"): cv.string,
    vol.Required("audio"): cv.string,
})
@callback
def ws_chunk(hass: HomeAssistant, connection: Any, msg: dict) -> None:
    """Forward one bounded PCMU audio payload to its session."""
    session = _state(hass)["sessions"].get(msg["session"])
    if session is None or session.owner is not connection:
        connection.send_error(msg["id"], "not_found", "Talkback session not found")
        return
    if len(msg["audio"]) > 900:
        connection.send_error(msg["id"], "invalid_format", "Audio packet too large")
        return
    try:
        audio = base64.b64decode(msg["audio"], validate=True)
    except (binascii.Error, ValueError):
        connection.send_error(msg["id"], "invalid_format", "Invalid base64 audio")
        return
    if len(audio) != 160:
        connection.send_error(msg["id"], "invalid_format", "Expected one 20 ms PCMU frame")
        return
    if session.audio_queue.full():
        try:
            session.audio_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    session.audio_queue.put_nowait(audio)
    session.last_audio = time.monotonic()
    session.packet_count += 1
    if session.packet_count % 50 == 0:
        elapsed = session.last_audio - session.started_at
        _LOGGER.info(
            "Talkback diagnostics: accepted %d PCMU frames over %.2f seconds",
            session.packet_count, elapsed,
        )
    connection.send_result(msg["id"])


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/ptt_stop",
    vol.Required("session"): cv.string,
})
@websocket_api.async_response
async def ws_stop(hass: HomeAssistant, connection: Any, msg: dict) -> None:
    """Stop a browser-owned microphone session."""
    session = _state(hass)["sessions"].get(msg["session"])
    if session is not None and session.owner is not connection:
        connection.send_error(msg["id"], "unauthorized", "Session belongs to another user")
        return
    if session is not None:
        await _end_session(hass, session.token)
    connection.send_result(msg["id"])


def async_register(hass: HomeAssistant) -> None:
    """Register commands once, shared by all bridge config entries."""
    if _STATE in hass.data[DOMAIN]:
        return
    hass.data[DOMAIN][_STATE] = {"sessions": {}, "starting": set()}
    websocket_api.async_register_command(hass, ws_start)
    websocket_api.async_register_command(hass, ws_chunk)
    websocket_api.async_register_command(hass, ws_stop)
    hass.data[DOMAIN][_STATE]["watchdog"] = hass.async_create_background_task(
        _watchdog(hass), f"{DOMAIN}_talkback_watchdog"
    )
