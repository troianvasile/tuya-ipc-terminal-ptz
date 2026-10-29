"""RTSP camera entities discovered from a standalone Tuya IPC Bridge."""
from __future__ import annotations

from urllib.parse import urlsplit

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def _camera_id(camera: dict) -> str | None:
    camera_id = camera.get("device_id")
    return camera_id if isinstance(camera_id, str) and camera_id else None


def _rtsp_url(manager_url: str, rtsp_port: int, path: str) -> str | None:
    parsed = urlsplit(manager_url)
    host = parsed.hostname
    if not host or not path.startswith("/") or not 1 <= rtsp_port <= 65535:
        return None
    if ":" in host:
        host = f"[{host}]"
    return f"rtsp://{host}:{rtsp_port}{path}"


def get_camera_rtsp_url(coordinator, camera_id: str) -> str | None:
    """Resolve one coordinator camera to its bridge RTSP address."""
    if coordinator is None or not coordinator.data:
        return None
    health = coordinator.data.get("health", {})
    if not isinstance(health, dict):
        return None
    for camera in coordinator.data.get("cameras", []):
        if _camera_id(camera) != camera_id:
            continue
        path = camera.get("path")
        port = health.get("rtsp_port", 8554)
        if isinstance(path, str) and isinstance(port, int):
            return _rtsp_url(coordinator.entry.data["url"], port, path)
    return None


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities) -> None:
    """Add cameras and discover further cameras on coordinator updates."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    known_ids: set[str] = set()

    def add_discovered_cameras() -> None:
        cameras = coordinator.data.get("cameras", []) if coordinator.data else []
        new_cameras = []
        for camera in cameras:
            camera_id = _camera_id(camera)
            if camera_id is not None and camera_id not in known_ids:
                known_ids.add(camera_id)
                new_cameras.append(BridgeCamera(coordinator, entry, camera_id))
        if new_cameras:
            async_add_entities(new_cameras)

    add_discovered_cameras()
    entry.async_on_unload(coordinator.async_add_listener(add_discovered_cameras))


class BridgeCamera(Camera):
    """A discovered Tuya RTSP stream exposed through Home Assistant."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_use_stream_for_stills = True

    def __init__(self, coordinator, entry: ConfigEntry, camera_id: str) -> None:
        super().__init__()
        self.coordinator = coordinator
        self.entry = entry
        self.camera_id = camera_id
        self._attr_unique_id = f"{entry.entry_id}_{camera_id}"

    def _camera(self) -> dict | None:
        for camera in self.coordinator.data.get("cameras", []) if self.coordinator.data else []:
            if _camera_id(camera) == self.camera_id:
                return camera
        return None

    @property
    def name(self) -> str:
        camera = self._camera()
        name = camera.get("name") if camera else None
        return name if isinstance(name, str) and name else "Tuya camera"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._camera() is not None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="Tuya IPC Bridge",
        )

    async def stream_source(self) -> str | None:
        """Return the bridge RTSP URL usable by HA's stream component."""
        return get_camera_rtsp_url(self.coordinator, self.camera_id)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still frame generated from the bridge RTSP source."""
        source = await self.stream_source()
        if source is None:
            return None
        return await async_get_image(self.hass, source, width=width, height=height)
