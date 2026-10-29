"""Bounded requests to the private Tuya IPC Bridge management API."""
from __future__ import annotations

import base64
import json
from urllib.request import Request, urlopen

from .const import CONF_PASSWORD, CONF_URL, CONF_USERNAME


def request_json(data: dict, path: str) -> dict:
    """Request a fixed management endpoint and return its JSON object."""
    credentials = (data[CONF_USERNAME] + ":" + data[CONF_PASSWORD]).encode()
    request = Request(
        data[CONF_URL].rstrip("/") + path,
        headers={"Authorization": "Basic " + base64.b64encode(credentials).decode()},
    )
    with urlopen(request, timeout=7) as response:
        payload = json.loads(response.read(65536))
    if not isinstance(payload, dict):
        raise ValueError("Unexpected bridge response")
    return payload


def fetch_health(data: dict) -> dict:
    """Fetch and validate bridge health."""
    payload = request_json(data, "/api/health")
    if payload.get("service") != "tuya-ipc-bridge":
        raise ValueError("Unexpected bridge response")
    return payload


def fetch_cameras(data: dict) -> list[dict]:
    """Fetch the public camera metadata exposed by the bridge."""
    payload = request_json(data, "/api/cameras")
    cameras = payload.get("cameras", [])
    if not isinstance(cameras, list):
        raise ValueError("Unexpected camera response")
    return [camera for camera in cameras if isinstance(camera, dict)]
