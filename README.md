# Tuya IPC Terminal + Little Elf: RTSP, two-way audio and Home Assistant

A community-maintained Go bridge for compatible Tuya/Little Elf IP cameras, with RTSP video/audio, an RTSP audio backchannel, browser push-to-talk (PTT) for Home Assistant, and optional PTZ controls. This is not an official Tuya or Home Assistant project.

**[Complete step-by-step installation](docs/PORTABLE_HOME_ASSISTANT_SETUP.md)** · **[Home Assistant setup](homeassistant/README.md)** · **[Troubleshooting](docs/TROUBLESHOOTING.md)** · **[Examples](examples/)**

> **Support status (October 2026):** The underlying Go RTSP/PTT lifecycle fixes were physically verified with two Little Elf cameras. The newly packaged Home Assistant frontend/backend and optional HTTP PTZ service have passing automated checks, but have **not yet passed an independent fresh-install / real-camera test**. Publishing on `main` makes the source available; it does not certify all Tuya cameras, firmware, regions or Home Assistant environments.

## Features and compatibility

| Feature | Status |
| --- | --- |
| Tuya web authentication and camera discovery | Implemented; use your actual account region |
| RTSP video + camera microphone (listening) | Implemented; tested on two Little Elf / SD H264 cameras |
| Browser microphone -> camera speaker (PTT) | Go bridge tested; portable HA package awaiting fresh-install verification |
| Speaker re-arm, RTP continuity, concurrent start and idle cleanup | Implemented; Go tests |
| HD/H265 and alternative audio codecs | Depends on camera/model; validate individually |
| PTZ CLI for six Tuya regional web hosts | Implemented with strict allowlist; **physically tested only in EU** |
| Optional HA PTZ controls on another host | Authenticated HTTP companion and HA REST example included; **disabled by default** |
| TTS/audio file injection into camera speaker | **Not supported/validated** |

The available Tuya web regions are `eu-central`, `eu-east`, `us-west`, `us-east`, `china` and `india`. The regional host allowlist is not a claim that PTZ was successfully tested in all six regions.

## Architecture

```text
Tuya/Little Elf camera <--- Tuya WebRTC + MQTT speaker/PTZ ---> Go bridge (Linux)
                                                |
                                      RTSP :8554 on private LAN/VPN
                                                |
                      +-------------------------+-------------------+
                      |                                             |
             Home Assistant/go2rtc                           HA Python PTT integration
              video + listening                              WebSocket <--- browser mic
                      |                                             |
            Lovelace WebRTC card                           PCMU/8000 RTSP backchannel
                                                                                  (same Go bridge)

Optional: HA rest_command -> HTTPS/VPN -> PTZ companion :8787 -> Tuya regional web API
```

The bridge and HA may be on **different machines or networks**, provided HA/go2rtc can reach the bridge over a trusted route. Do not copy the `172.17.0.1` Docker IP from somebody else's setup.

## Requirements

- Compatible Tuya/Little Elf camera accessible with a Tuya web account (camera discovery and cloud signalling must work).
- A Linux host with Git, **Go 1.23+** and network access to Tuya and the camera.
- Home Assistant for the optional browser PTT package; HTTPS/localhost, microphone permission and a browser with AudioWorklet.
- For listening/video in Lovelace: [AlexxIT WebRTC Camera](https://github.com/AlexxIT/WebRTC) (installed separately) and an accessible RTSP stream.
- For the packaged PTT encoder: camera RTSP talkback must advertise **PCMU/8000**. This path is not a universal codec transcoder.
- TCP **8554** on the Go host reachable privately from HA/go2rtc. It is **unauthenticated, unencrypted RTSP**: firewall or VPN it; **do not expose publicly**.

## Quick start: Go bridge (new installation)

Use a **new, dedicated directory** and the same account and working directory for authentication, discovery and the systemd service.

```bash
git clone https://github.com/troianvasile/tuya-ipc-terminal-ptz.git
cd tuya-ipc-terminal-ptz
go version
go test ./...
go build -o tuya-ipc-terminal .

# Discover supported web regions:
./tuya-ipc-terminal auth show-regions

# Replace region/email with your own account. QR login is interactive:
./tuya-ipc-terminal auth add eu-central user@example.com
# Or use the password flow (not an unattended CLI flag with a password):
# ./tuya-ipc-terminal auth add eu-central user@example.com --password

./tuya-ipc-terminal auth test eu-central user@example.com
./tuya-ipc-terminal cameras refresh
./tuya-ipc-terminal cameras list
./tuya-ipc-terminal rtsp list-endpoints

# Foreground first, to verify the logs and camera negotiation:
./tuya-ipc-terminal rtsp start --port 8554
```

The bridge saves session cookies and camera registry in `.tuya-data/` under the **current working directory**. Never commit this directory. Do not change the user/directory between setup and systemd.

After verifying the stream, install a persistent service using [`examples/tuya-ipc-rtsp.service.example`](examples/tuya-ipc-rtsp.service.example), replacing `INSTALL_DIR` and `SERVICE_USER`. Restart/boot persistence is checked separately in the complete guide.

Example stream URLs (use the **discovered RTSP path**, not the display name verbatim):

```text
rtsp://BRIDGE_PRIVATE_IP:8554/Front_Door/sd
rtsp://BRIDGE_PRIVATE_IP:8554/Front_Door/hd
```

## Quick start: Home Assistant PTT

Once the Go stream works, read [the detailed HA instructions](homeassistant/README.md).

On the computer with access to the **actual HA configuration directory**:

```bash
# If the repository was cloned in the previous step:
bash homeassistant/install.sh /path/to/homeassistant/config
```

For Docker, use the **host folder mapped to /config**; for HA OS, install/copy the files under `/config` using an appropriate file/SSH add-on. The installer backs up existing integration/card files; it **does not restart HA**.

Merge the following example into HA's `configuration.yaml` (replace the IP and discovered path; choose any unique local alias):

```yaml
little_elf_talk:
  admin_only: true
  cameras:
    front_door:
      rtsp_url: rtsp://192.168.1.50:8554/Front_Door/sd
```

Validate configuration and restart HA manually. Add the **JavaScript module** resource `/local/little-elf-ptt-card.js?v=0.1.0` in the Lovelace resource settings. The installer also supplies `/local/little-elf-talk-processor.js`, which the card loads itself.

Inside a Lovelace view:

```yaml
type: vertical-stack
cards:
  - type: custom:webrtc-camera
    url: rtsp://192.168.1.50:8554/Front_Door/sd
    mode: mse,hls
    media: video,audio
    ui: true
  - type: custom:little-elf-ptt-card
    camera: front_door
```

`camera: front_door` is the **HA alias** from `little_elf_talk.cameras`, not necessarily the camera display name. PTT uses the authenticated HA WebSocket; microphone data is sent to HA, then over private RTSP to the Go bridge. Do **not** configure go2rtc TTS/file injection.

## Optional PTZ: CLI and Home Assistant

```bash
# Run in the same bridge working directory as auth/camera discovery:
./tuya-ipc-terminal ptz move --camera "Front Door" --direction LEFT --duration 400ms
./tuya-ipc-terminal ptz stop --camera "Front Door"
```

The camera argument is the **discovered Tuya display name or device ID** (not the HA PTT alias). PTZ uses a reverse-engineered vendor endpoint; test short movements and keep its path clear.

To control PTZ from **another HA host**, launch the separately configured `./tuya-ipc-terminal ptz serve` companion (binds `127.0.0.1:8787` by default) with a secret bearer token. Configure HTTPS/VPN/private routing, then merge [`homeassistant/ptz-rest-command.yaml.example`](homeassistant/ptz-rest-command.yaml.example) and pass `camera` / `direction` in the Lovelace button. **Do not run the companion openly over HTTP on the internet.** See [complete PTZ instructions](docs/PORTABLE_HOME_ASSISTANT_SETUP.md#7-optional-ptz-for-home-assistant).

## Commands and files

| Command | Purpose |
| --- | --- |
| `auth add REGION EMAIL` | QR/password login |
| `auth test REGION EMAIL` | Check saved account session |
| `auth show-regions` | Show regional endpoints |
| `cameras refresh` / `cameras list` | Discover/list cameras |
| `cameras info NAME_OR_ID` | Inspect camera capabilities |
| `rtsp start --port 8554` | Run the RTSP server (foreground) |
| `rtsp list-endpoints` | Show discovered RTSP paths |
| `ptz move --camera NAME --direction UP --duration 400ms` | Bounded PTZ move |
| `ptz stop --camera NAME` | Send PTZ stop |
| `ptz serve --listen 127.0.0.1:8787` | Optional bearer-protected PTZ API |

Source layout: `pkg/rtsp/` (bridge and RTP), `cmd/auth` / `cmd/cameras` / `cmd/ptz`, `homeassistant/custom_components/little_elf_talk/`, `homeassistant/www/`, `homeassistant/install.sh`, `examples/`, `docs/`.

## Tests and development

```bash
go test ./...
go vet ./...
python3 -m compileall -q homeassistant/custom_components/little_elf_talk homeassistant/tests
python3 -m unittest discover -s homeassistant/tests -p 'test_*.py' -v
node --check homeassistant/www/little-elf-ptt-card.js
node --check homeassistant/www/little-elf-talk-processor.js
```

[GitHub Actions](.github/workflows/portable-ci.yml) runs these automated checks. They test source compatibility and the RTSP wire format, **not** an actual Home Assistant installation, device speaker, browser permissions or non-EU PTZ.

## Security, limitations and help

- Bind/firewall RTSP to trusted LAN/VPN. The Go listener defaults to **all interfaces**; it does not have RTSP authentication or TLS.
- The PTZ companion needs a **minimum 32-character token**; use HTTPS/private routing for HA-to-PTZ traffic, and keep token values in HA `secrets.yaml`.
- Saved Tuya sessions/credentials live in `.tuya-data/`. Store with private filesystem permissions.
- Browser microphone requires HTTPS (or localhost) and permission. The portable HA backend defaults to admin-only PTT.
- Some Tuya models/firmware, regions or codec variants may fail. PCMU/8000 talkback is the currently targeted path.
- TTS speaker playback is not validated and is not a feature of this installation.
- For failures, see [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md). Remove credentials, cookies, tokens, private IPs and camera device IDs from shared logs.
- The Go bridge supports signalling through Tuya web services; it is **not an entirely offline camera implementation**.

## Credits and license

Derived from [seydx/tuya-ipc-terminal](https://github.com/seydx/tuya-ipc-terminal) and the [yangyongyongyong fixed fork](https://github.com/yangyongyongyong/tuya-ipc-terminal-fixed), with additional SD, RTSP/talkback, lifecycle and PTZ changes. See [MIT LICENSE](LICENSE). Reverse-engineered Tuya APIs are subject to change; review vendor terms and your privacy/legal requirements. No affiliation with Tuya, Little Elf or Home Assistant.

[Report a reproducible issue](https://github.com/troianvasile/tuya-ipc-terminal-ptz/issues) with OS, HA/browser versions, camera capabilities/codec information, sanitized logs and exact reproduction steps.
