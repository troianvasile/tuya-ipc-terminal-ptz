"""Wire-level tests for the portable RTSP backchannel, no HA installation needed."""
import asyncio
import importlib.util
import pathlib
import struct
import unittest

SOURCE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components" / "little_elf_talk" / "rtsp_audio.py"
)
spec = importlib.util.spec_from_file_location("little_elf_rtsp", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RtspPcmuBackchannel = module.RtspPcmuBackchannel
RtspError = module.RtspError

SDP = (
    "v=0\r\n"
    "m=video 0 RTP/AVP 96\r\n"
    "a=control:rtsp://localhost:8554/Front_Door/sd/video\r\n"
    "m=audio 0 RTP/AVP 0\r\n"
    "a=rtpmap:0 PCMU/8000\r\n"
    "a=control:rtsp://localhost:8554/Front_Door/sd/audio\r\n"
    "m=audio 0 RTP/AVP 0\r\n"
    "a=rtpmap:0 PCMU/8000\r\n"
    "a=control:rtsp://localhost:8554/Front_Door/sd/backchannel\r\n"
)

class RtspBackchannelTest(unittest.IsolatedAsyncioTestCase):
    def test_sdp(self):
        path, codec = RtspPcmuBackchannel._backchannel_from_sdp(SDP)
        self.assertTrue(path.endswith("/backchannel"))
        self.assertEqual(codec, 0)

    def test_unsupported_codec(self):
        bad = SDP.replace("RTP/AVP 0", "RTP/AVP 8").replace("PCMU/8000", "PCMA/8000")
        with self.assertRaises(RtspError):
            RtspPcmuBackchannel._backchannel_from_sdp(bad)

    def test_url_validation(self):
        for url in (
            "https://host/test", "rtsp://user:pw@host/video",
            "rtsp://host/path?key=secret", "rtsp:///path",
        ):
            with self.assertRaises(ValueError):
                RtspPcmuBackchannel(url)

    async def test_rtsp_setup_and_interleaved_pcmu(self):
        captured = asyncio.Future()

        async def handle(reader, writer):
            try:
                describe = await reader.readuntil(b"\r\n\r\n")
                self.assertIn(b"DESCRIBE", describe)
                body = SDP.encode("ascii")
                writer.write(
                    b"RTSP/1.0 200 OK\r\nCSeq: 1\r\n"
                    + f"Content-Length: {len(body)}\r\n".encode("ascii")
                    + b"\r\n" + body
                )
                await writer.drain()

                setup = await reader.readuntil(b"\r\n\r\n")
                self.assertIn(b"/backchannel RTSP/1.0", setup)
                self.assertIn(b"interleaved=4-5", setup)
                writer.write(
                    b"RTSP/1.0 200 OK\r\nCSeq: 2\r\n"
                    b"Session: test-session;timeout=60\r\n"
                    b"Transport: RTP/AVP/TCP;unicast;interleaved=4-5\r\n\r\n"
                )
                await writer.drain()

                # First media can arrive before the sender starts writing RTP.
                writer.write(b"$" + bytes([2]) + struct.pack("!H", 3) + b"abc")
                await writer.drain()

                header = await reader.readexactly(4)
                self.assertEqual(header[0], 36)
                self.assertEqual(header[1], 4)
                length = struct.unpack("!H", header[2:4])[0]
                data = await reader.readexactly(length)
                captured.set_result(data)
                await reader.read()
            except Exception as err:
                if not captured.done():
                    captured.set_exception(err)
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            client = RtspPcmuBackchannel(
                f"rtsp://127.0.0.1:{port}/Front_Door/sd"
            )
            await client.start()
            await client.write_pcmu(bytes([0xFF]) * 160)
            data = await asyncio.wait_for(captured, timeout=3)
            self.assertEqual(len(data), 12 + 160)
            version, payload, seq, ts, ssrc = struct.unpack("!BBHII", data[:12])
            self.assertEqual(version, 0x80)
            self.assertEqual(payload & 0x7F, 0)
            self.assertTrue(ssrc >= 0)
            self.assertEqual(data[12:], bytes([0xFF]) * 160)
            await client.close()
        finally:
            server.close()
            await server.wait_closed()

if __name__ == "__main__":
    unittest.main()
