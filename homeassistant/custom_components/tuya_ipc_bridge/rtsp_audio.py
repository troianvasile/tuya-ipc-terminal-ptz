"""Minimal async RTSP PCMU backchannel client for the Tuya bridge."""
from __future__ import annotations

import asyncio
import re
import secrets
import struct
from urllib.parse import urlsplit

_MAX_RESPONSE = 64 * 1024


class RtspError(Exception):
    """RTSP setup or forwarding failed."""


class RtspPcmuBackchannel:
    """One RTSP/TCP backchannel connection per microphone press."""

    def __init__(self, url: str) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "rtsp" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
        ):
            raise ValueError("Expected a plain RTSP URL without credentials")
        self.url = url
        self.host = parsed.hostname
        self.port = parsed.port or 554
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.channel = 4
        self._cseq = 0
        self._payload_type = 0
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
            control, self._payload_type = self._backchannel_from_sdp(
                body.decode("utf-8", "replace")
            )
            setup_url = control if control.startswith("rtsp://") else (
                self.url.rstrip("/") + "/" + control.lstrip("/")
            )
            status, headers, _ = await self._request(
                "SETUP", setup_url,
                {"Transport": "RTP/AVP/TCP;unicast;interleaved=4-5"},
            )
            if status != 200:
                raise RtspError(f"SETUP returned {status}")
            if not headers.get("session"):
                raise RtspError("RTSP SETUP did not return a Session header")
            match = re.search(r"interleaved=(\d+)-(\d+)", headers.get("transport", ""), re.I)
            if not match:
                raise RtspError("Server did not negotiate interleaved RTP")
            self.channel = int(match.group(1))
            self._rx_task = asyncio.create_task(self._drain_incoming())
        except BaseException:
            await self.close()
            raise

    @staticmethod
    def _backchannel_from_sdp(sdp: str) -> tuple[str, int]:
        for section in sdp.replace("\r", "").split("\nm=")[1:]:
            lines = section.strip().split("\n")
            if not lines or not lines[0].startswith("audio "):
                continue
            control = next((line[10:] for line in lines[1:]
                            if line.startswith("a=control:") and "backchannel" in line), None)
            if not control:
                continue
            for fmt in lines[0].split()[3:]:
                codec = f"a=rtpmap:{fmt} PCMU/8000"
                if fmt == "0" or any(line.upper() == codec.upper() for line in lines[1:]):
                    return control, int(fmt)
            raise RtspError("Camera RTSP backchannel is not PCMU/8000")
        raise RtspError("No RTSP audio backchannel advertised")

    async def _request(self, method: str, url: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        if self.reader is None or self.writer is None:
            raise RtspError("RTSP connection is not open")
        self._cseq += 1
        lines = [f"{method} {url} RTSP/1.0", f"CSeq: {self._cseq}", "User-Agent: TuyaIPCBridge/0.1"]
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
            key, separator, value = line.decode("latin-1").partition(":")
            if separator:
                result[key.strip().lower()] = value.strip()
        try:
            body_length = int(result.get("content-length", "0"))
        except ValueError as exc:
            raise RtspError("Invalid RTSP Content-Length") from exc
        if body_length < 0 or body_length > _MAX_RESPONSE:
            raise RtspError("RTSP response body too large")
        body = await asyncio.wait_for(self.reader.readexactly(body_length), timeout=8) if body_length else b""
        return status, result, body

    async def _drain_incoming(self) -> None:
        try:
            while self.reader and not self.reader.at_eof():
                if not await self.reader.read(16384):
                    break
        except (OSError, asyncio.CancelledError):
            pass

    async def write_pcmu(self, samples: bytes) -> None:
        if self._closed or self.writer is None:
            raise RtspError("Talkback session is closed")
        if not samples or len(samples) > 640:
            raise ValueError("Expected 1-640 PCMU samples")
        packet = struct.pack(
            "!BBHII", 0x80, self._payload_type & 0x7F,
            self._sequence, self._timestamp, self._ssrc,
        ) + samples
        self.writer.write(
            b"$" + bytes([self.channel]) + struct.pack("!H", len(packet)) + packet
        )
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
        if self.writer:
            self.writer.close()
            try:
                await asyncio.wait_for(self.writer.wait_closed(), timeout=2)
            except (asyncio.TimeoutError, ConnectionError, OSError):
                pass
            self.writer = None
