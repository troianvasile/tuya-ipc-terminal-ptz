"""Wire-level regression tests for Tuya IPC Bridge talkback transport."""
import asyncio
import importlib.util
import pathlib
import struct
import unittest


SOURCE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "tuya_ipc_bridge"
    / "rtsp_audio.py"
)
spec = importlib.util.spec_from_file_location("tuya_ipc_rtsp", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RtspPcmuBackchannel = module.RtspPcmuBackchannel


class RtspBackchannelTest(unittest.IsolatedAsyncioTestCase):
    async def test_uses_legacy_camera_backchannel_sequence(self):
        captured = asyncio.Future()

        async def handle(reader, writer):
            try:
                describe = await reader.readuntil(b"\r\n\r\n")
                self.assertIn(b"DESCRIBE", describe)
                writer.write(b"RTSP/1.0 200 OK\r\nCSeq: 1\r\n\r\n")
                await writer.drain()

                setup = await reader.readuntil(b"\r\n\r\n")
                self.assertIn(b"SETUP rtsp://127.0.0.1", setup)
                self.assertIn(b"/backchannel RTSP/1.0", setup)
                self.assertIn(b"interleaved=4-5", setup)
                writer.write(
                    b"RTSP/1.0 200 OK\r\nCSeq: 2\r\n"
                    b"Session: test-session;timeout=60\r\n"
                    b"Transport: RTP/AVP/TCP;unicast;interleaved=4-5\r\n\r\n"
                )
                await writer.drain()

                play = await reader.readuntil(b"\r\n\r\n")
                self.assertIn(b"PLAY rtsp://127.0.0.1", play)
                self.assertIn(b"Session: test-session", play)
                writer.write(b"RTSP/1.0 200 OK\r\nCSeq: 3\r\n\r\n")
                await writer.drain()

                header = await reader.readexactly(4)
                self.assertEqual(header[:2], b"$\x04")
                payload = await reader.readexactly(struct.unpack("!H", header[2:])[0])
                captured.set_result(payload)
            except Exception as err:
                if not captured.done():
                    captured.set_exception(err)
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            client = RtspPcmuBackchannel(f"rtsp://127.0.0.1:{port}/camera")
            await client.start()
            await client.write_pcmu(bytes([0xFF]) * 160)
            packet = await asyncio.wait_for(captured, timeout=3)
            version, payload_type, _, _, _ = struct.unpack("!BBHII", packet[:12])
            self.assertEqual(version, 0x80)
            self.assertEqual(payload_type, 0x80)
            self.assertEqual(packet[12:], bytes([0xFF]) * 160)
            await client.close()
        finally:
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
