# RTSP implementation comparison

The upstream Home Assistant app by [YaannnTech](https://github.com/YaannnTech/HA-Apps/tree/main/tuya_ipc_bridge)
builds a separate fork of `seydx/tuya-ipc-terminal`. This branch retains the
existing **PTT/PTZ-enabled** fork and its stream-lifecycle fixes. Changes are
assessed individually rather than merging their Go source wholesale.

| Feature | This repository's existing Go implementation | Action |
| --- | --- | --- |
| Case-insensitive camera lookup | `findCameraByRTSPPath` already uses `strings.EqualFold` | Keep and test |
| Video RTP payload type normalization (HD/HEVC) | Current fork needs wire-level verification | Test before further change |
| UDP RTP sent to client IP, not localhost | Current `AddUDPClient` has no client-host argument; implementation uses localhost | Port carefully with SETUP caller signature changes and tests |
| RTSP connection startup responsiveness | Existing asynchronous stream-start and lifecycle fixes | Regression test against slow Tuya signalling |
| Dead TCP client cleanup | Existing RTSP backchannel/forwarder diverges substantially from YaannnTech | Port/review independently, preserve PTT |
| Session-expiry notification | New `deploy/manage.py` provides optional HA REST notification | Add integration tests |

## Do not merge blindly

The YaannnTech forwarder has an API `AddUDPClient(sessionID, clientHost,...)`
that differs from this fork's `AddUDPClient(sessionID, videoRTPPort, audioRTPPort)`.
Replacing entire files would risk breaking RTSP backchannel audio. Validate
individual patches and peer interactions before porting.

The Supervisor add-on's `/app/<slug>`, `SUPERVISOR_TOKEN`, `bashio` and
`http://supervisor` assumptions are deliberately **not used** here.

## Testing required

- Fresh Docker Compose build and login with Tuya Smart or Little Elf.
- RTSP SD/H264 and HD/H265: OPTIONS/DESCRIBE/SETUP/PLAY, browser and VLC.
- TCP reconnect/disconnect and multiple clients.
- UDP client with a non-loopback IP.
- PCMU/8000 RTSP backchannel into camera speaker.
- Browser microphone permission and HA PTT.
- PTZ movement and stop, EU and other regions where available.
- Authentication expiration/reauthentication and HA notifications.
- No impact on running systemd production instance.

This branch is **experimental**, not production-ready. Tests in CI are source
checks only; no real Tuya cameras are available to GitHub runners.
