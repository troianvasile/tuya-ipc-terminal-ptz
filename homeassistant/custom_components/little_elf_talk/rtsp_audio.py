"""Minimal async RTSP PCMU backchannel client for the Tuya Go bridge.

The connection sends only microphone audio; the normal HA player handles video.
No shell commands, FFmpeg binary or go2rtc push API are required.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import struct
from urllib.parse import urlsplit

_LOGGER = logging.getLogger(__name__)
_MAX_RESPONSE = 64 * 1024


class RtspError(Exception):
    """RTSP setup or forwarding failed."""


class RtspPcmuBackchannel:
    """One RTSP/TCP backchannel connection per microphone press."""

    def __init__(self, url: str) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "rtsp"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("rtsp_url must be a plain rtsp://host:port/path without credentials")
        self.url = url
        self.host = parsed.hostname
        self.port = parsed.port or 554
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.session = ""
        self.channel = 4
        self._cseq = 0
        self._sequence = secrets.randbelow(65536)
        self._timestamp = secrets.randbits(32)
        self._ssrc = secrets.randbits(32)
        self._rx_task: asyncio.Task | None = None
        self._closed = False
        self._packets = 0

    async def start(self) -> None:
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=7
            )
            status, _, body = await self._request(
                "DESCRIBE", self.url, {"Accept": "application/sdp"}
            )
            if status != 200:
                raise RtspError(f"DESCRIBE returned {status}")
            sdp = body.decode("utf-8", "replace")
            backchannel, payload_type = self._backchannel_from_sdp(sdp)
            self._payload_type = payload_type
            setup_url = backchannel if backchannel.startswith("rtsp://") else (
                self.url.rstrip("/") + "/" + backchannel.lstrip("/")
            )
            status, headers, _ = await self._request(
                "SETUP", setup_url,
                {"Transport": "RTP/AVP/TCP;unicast;interleaved=4-5"}
            )
            if status != 200:
                raise RtspError(f"SETUP returned {status}")
            self.session = headers.get("session", "").split(";", 1)[0].strip()
            if not self.session:
                raise RtspError("RTSP SETUP did not return a Session header")
            transport = headers.get("transport", "")
            if "interleaved=" not in transport.lower():
                raise RtspError("Server did not negotiate interleaved RTP")
            import re
            match = re.search(r"interleaved=(\\d+)-(\\d+)", transport, re.I)
            if not match:
                raise RtspError("Malformed interleaved RTP transport")
            self.channel = int(match.group(1))
            status, _, _ = await self._request(
                "PLAY", self.url, {"Session": self.session}
            )
            if status != 200:
                raise RtspError(f"PLAY returned {status}")
            # The bridge may forward camera media on the same TCP socket.
            # Drain it continuously; otherwise the remote socket can stall.
            self._rx_task = asyncio.create_task(self._drain_incoming())
        except BaseException:
            await self.close()
            raise

    @staticmethod
    def _backchannel_from_sdp(sdp: str) -> tuple[str, int]:
        """Find the PCMU/8000 outbound track; reject unsupported audio."""
        sections = sdp.replace("\r", "").split("\nm=")
        for section in sections[1:]:
            lines = section.strip().split("\n")
            if not lines or not lines[0].startswith("audio "):
                continue
            control = next(
                (line[10:] for line in lines[1:]
                 if line.startswith("a=control:") and "backchannel" in line),
                None,
            )
            if not control:
                continue
            formats = lines[0].split()[3:]
            for fmt in formats:
                codec = f"a=rtpmap:{fmt} PCMU/8000"
                if fmt == "0" or any(
                    line.upper() == codec.upper() for line in lines[1:]
                ):
                    return control, int(fmt)
            raise RtspError("Camera RTSP backchannel is not PCMU/8000")
        raise RtspError("No RTSP audio backchannel advertised")

    async def _request(
        self, method: str, url: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        if not self.writer or not self.reader:
            raise RtspError("RTSP connection is not open")
        self._cseq += 1
        lines = [
            f"{method} {url} RTSP/1.0",
            f"CSeq: {self._cseq}",
            "User-Agent: LittleElfHomeAssistant/0.1",
        ]
        lines += [f"{key}: {value}" for key, value in (headers or {}).items()]
        self.writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
        await asyncio.wait_for(self.writer.drain(), timeout=5)
        status_line = await asyncio.wait_for(self.reader.readline(), timeout=8)
        if len(status_line) > 1024 or not status_line.startswith(b"RTSP/1.0 "):
            raise RtspError("Invalid RTSP status line")
        try:
            status = int(status_line.split()[1])
        except (IndexError, ValueError) as exc:
            raise RtspError("Invalid RTSP status code") from exc
        result: dict[str, str] = {}
        total = len(status_line)
        while True:
            line = await asyncio.wait_for(self.reader.readline(), timeout=8)
            total += len(line)
            if not line or total > _MAX_RESPONSE:
                raise RtspError("RTSP response headers truncated or too large")
            if line in (b"\r\n", b"\n"):
                break
            key, sep, value = line.decode("latin-1").partition(":")
            if sep:
                result[key.strip().lower()] = value.strip()
        try:
            body_length = int(result.get("content-length", "0"))
        except ValueError as exc:
            raise RtspError("Invalid RTSP Content-Length") from exc
        if body_length < 0 or body_length > _MAX_RESPONSE:
            raise RtspError("RTSP response body too large")
        body = await asyncio.wait_for(
            self.reader.readexactly(body_length), timeout=8
        ) if body_length else b""
        return status, result, body

    async def _drain_incoming(self) -> None:
        try:
            while self.reader and not self.reader.at_eof():
                if not await self.reader.read(16384):
                    break
        except (OSError, asyncio.CancelledError):
            pass

    async def write_pcmu(self, samples: bytes) -> None:
        if self._closed or not self.writer:
            raise RtspError("Talkback session is closed")
        if not samples or len(samples) > 640:
            raise ValueError("Expected 1-640 PCMU samples")
        header = struct.pack(
            "!BBHII", 0x80, self._payload_type & 0x7F,
            self._sequence, self._timestamp, self._ssrc
        )
        payload = header + samples
        self.writer.write(b"$" + bytes([self.channel]) + struct.pack("!H", len(payload)) + payload)
        self._sequence = (self._sequence + 1) & 0xFFFF
        self._timestamp = (self._timestamp + len(samples)) & 0xFFFFFFFF
        self._packets += 1
        if self._packets % 5 == 0:
            await asyncio.wait_for(self.writer.drain(), timeout=2)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._rx_task:
            self._rx_task.cancel()
            self._rx_task = None
        # TEARDOWN is optional; closing TCP is sufficient to release bridge.
        if self.writer:
            self.writer.close()
            try:
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2)
            except (asyncio.TimeoutError, ConnectionError, OSError):
                pass
            self.writer = None
