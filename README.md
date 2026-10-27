# Tuya IPC Terminal + PTZ

A community-maintained command-line bridge for compatible Tuya-based IP cameras. It exposes camera streams over RTSP and adds **experimental pan/tilt (PTZ) control** through the authenticated Tuya / Little Elf web interface.

> **Unofficial project.** Not affiliated with Tuya, Smart Life, or Little Elf. Streaming compatibility varies by camera, firmware, account and region. PTZ is currently implemented only for the EU web host `protect-eu.ismartlife.me`.

## Features

- WebRTC-to-RTSP bridge with HD and SD stream paths where available
- Saved-session authentication and camera discovery
- Multiple accounts, RTSP clients and supported camera streams
- Stability improvements inherited from the fixed fork (SDP selection, reconnection/teardown, disconnected-client cleanup)
- CLI PTZ movement in cardinal or diagonal directions, with a bounded duration and an automatic STOP attempt

## Project origins and credits

This repository builds on these open-source projects:

1. **[seydx/tuya-ipc-terminal](https://github.com/seydx/tuya-ipc-terminal)** — original Tuya camera CLI and WebRTC-to-RTSP bridge.
2. **[yangyongyongyong/tuya-ipc-terminal-fixed](https://github.com/yangyongyongyong/tuya-ipc-terminal-fixed)** — streaming stability and reconnection fixes.
3. **This derivative** — PTZ commands using existing saved browser-session cookies and the web PTZ start/end endpoints, plus subsequent PTZ reliability improvements and tests.

Earlier work remains credited through Git history and the retained [MIT license](LICENSE). Please keep these notices if you redistribute this project.

## Requirements

- Go **1.23.x or newer**, as specified by [go.mod](go.mod)
- Network connectivity to the camera and required Tuya services
- A supported account with a working authenticated session
- A compatible Tuya-based camera (PTZ-capable hardware is required for movement)
- Optionally, `ffplay` (FFmpeg) or another RTSP player to view streams

## Installation

```bash
git clone https://github.com/troianvasile/tuya-ipc-terminal-ptz.git
cd tuya-ipc-terminal-ptz

# Builds ./tuya-ipc-terminal
chmod +x build.sh
./build.sh

./tuya-ipc-terminal --help
```

Alternatively, build directly with `go build -o tuya-ipc-terminal .`.

> Building does not configure accounts or start a service. Authentication data is generated locally after sign-in; **never commit or upload it**.

## Quick start

### 1. Authenticate

Choose a region supported by your account:

```bash
./tuya-ipc-terminal auth show-regions
./tuya-ipc-terminal auth add eu-central user@example.com
```

For interactive email/password authentication where supported:

```bash
./tuya-ipc-terminal auth add eu-central user@example.com --password
```

Other useful commands:

```bash
./tuya-ipc-terminal auth list
./tuya-ipc-terminal auth test eu-central user@example.com
./tuya-ipc-terminal auth refresh eu-central user@example.com
```

### 2. Discover cameras

```bash
./tuya-ipc-terminal cameras refresh
./tuya-ipc-terminal cameras list
./tuya-ipc-terminal cameras info Camera01
```

Replace `Camera01` with a discovered camera name or device ID. Use a device ID when names are ambiguous.

### 3. Start and view RTSP

```bash
./tuya-ipc-terminal rtsp start --port 8554

# From another terminal, after checking available endpoints:
./tuya-ipc-terminal rtsp list-endpoints
ffplay rtsp://127.0.0.1:8554/Camera01/sd
```

Typical endpoint shapes are `rtsp://HOST:8554/CAMERA_NAME` and `rtsp://HOST:8554/CAMERA_NAME/sd`. Use the paths actually reported by `rtsp list-endpoints`; availability and codecs depend on the device.

```bash
./tuya-ipc-terminal rtsp status
./tuya-ipc-terminal rtsp stop
```

## PTZ: pan and tilt

PTZ uses the same saved web session as the CLI. It does **not** require a separate Tuya IoT developer project. The current implementation accepts only sessions with the server host `protect-eu.ismartlife.me`; the wider set of streaming/authentication regions does **not** imply PTZ support in those regions.

```bash
# Move left for 400 ms, then attempt to stop
./tuya-ipc-terminal ptz move --camera Camera01 --direction LEFT --duration 400ms

# Another camera, using its device ID instead of a name
./tuya-ipc-terminal ptz move --camera CAMERA_DEVICE_ID --direction UP --duration 300ms

# Explicit STOP command
./tuya-ipc-terminal ptz stop --camera Camera01
```

Supported direction values: `UP`, `DOWN`, `LEFT`, `RIGHT`, `UP_LEFT`, `UP_RIGHT`, `DOWN_LEFT`, `DOWN_RIGHT`. Hyphens and lowercase input are normalized by the CLI. Diagonal support depends on the device and has not been established across models.

Allowed movement duration: **100 ms to 1500 ms**; default **400 ms**. Start with short movements. The CLI tries to issue STOP after each movement, including when START reports an error. In the improved implementation a failed STOP causes a nonzero command result; a cloud outage, killed process or lost network may still prevent an actual stop.

**Do not assume PTZ is safe for unattended continuous motion.** Avoid obstacles and do not expose unauthenticated remote control endpoints.

### PTZ API behavior

Internally, the PTZ command sends authenticated HTTPS POSTs to:

- `/api/jarvis/ptz/start` with `devId` and `direction`
- `/api/jarvis/ptz/end` with `devId`

These are reverse-engineered web endpoints, not a documented public PTZ API. Vendor updates may change their behavior.

## Compatibility

| Capability | Scope |
| --- | --- |
| Authentication and RTSP | Several regions are exposed by the underlying tool; actual device compatibility varies |
| PTZ | Implemented for the `protect-eu.ismartlife.me` session host only |
| PTZ hardware | Requires a camera that supports pan/tilt |
| Physical PTZ validation | Confirmed with two compatible Little Elf cameras on the EU endpoint |
| Other regions and camera models | Not verified for PTZ |
| Audio and codecs | Depend on the camera and receiving player; transcoding may be necessary |

PTZ is **experimental**. Please report reproducible device/region results without disclosing identifying account data.

## Integrations

Use any RTSP-capable client (for example FFmpeg/ffplay, go2rtc, an NVR, or home-automation software). In networked/container installations, replace `127.0.0.1` with an address reachable from the client.

Example go2rtc configuration (substitute a valid endpoint from `rtsp list-endpoints`):

```yaml
streams:
  camera_01:
    - rtsp://RTSP_HOST:8554/Camera01/sd
```

This repository provides a **CLI**, not a built-in HTTP PTZ service or a Home Assistant integration. Automations can invoke the CLI through their own secure, locally managed command runner; do not expose saved sessions or a shell command endpoint to the internet.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| No cameras listed | Verify the selected account/region, test the session, then run `cameras refresh` |
| RTSP player cannot connect | Check `rtsp status`, `rtsp list-endpoints`, network/firewall and actual stream path |
| Video starts but will not resume | Check bridge logs and try the SD endpoint; provide a sanitized report |
| PTZ reports an untrusted host | PTZ currently supports only the EU host noted above |
| PTZ command is rejected | Check that the camera supports PTZ, account permissions, and that its saved session is still valid |
| STOP fails | Stop using repeated movement commands; check network and the camera's vendor app before retrying |

Never post session JSON files, cookies, passwords, email addresses, private camera IDs or unredacted logs in a public issue.

## Development and testing

```bash
go test ./...
go build -o tuya-ipc-terminal .
```

The PTZ tests use HTTP mocks and exercise request handling and timed-movement error behavior; they do not replace physical hardware tests. When proposing changes, describe the affected region, camera category, expected behavior, and sanitized reproduction steps.

## Security and privacy

- Session state is stored locally (including files in `.tuya-data/`); treat it as a credential.
- Keep the session directory private, and never commit it, even to a private repository.
- Protect RTSP access with firewall/network isolation as appropriate; RTSP feeds may be unencrypted.
- Consider revoking and reauthenticating sessions if credentials or cookies are exposed.

## License and disclaimer

Released under the [MIT license](LICENSE), retaining the original copyright notice and credit for prior contributions.

This is an unofficial reverse-engineering project. Use it only with cameras and accounts you are authorized to access, and comply with applicable laws and provider terms. No availability, feature compatibility or security guarantee is provided.

## Support and contributions

Search [issues](https://github.com/troianvasile/tuya-ipc-terminal-ptz/issues) before filing a new report. Include your operating system, Go version, camera category/firmware (if known), region, relevant commands, expected vs. observed behavior and **sanitized** error messages. Pull requests with targeted tests and clear compatibility notes are welcome.
