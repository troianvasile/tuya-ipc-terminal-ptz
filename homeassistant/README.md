# Home Assistant: Little Elf two-way audio installation

**Quick link:** [complete setup from a clean Linux server](../docs/PORTABLE_HOME_ASSISTANT_SETUP.md) · [root README](../README.md) · [troubleshooting](../docs/TROUBLESHOOTING.md).

This folder contains a YAML-configured **portable Home Assistant push-to-talk (PTT) preview**. It does not replace the Go RTSP bridge. It adds browser microphone capture -> authenticated Home Assistant WebSocket -> PCMU/8000 RTSP talkback on a chosen camera.

> **Compatibility warning:** The Go bridge/PTT fixes were physically tested with two Little Elf cameras, but this **newly packaged HA integration/card is not a byte-for-byte copy of that working private instance**. Automated Python wire-format and JS syntax tests pass; a *fresh-install live test* is still required. TTS/file playback is not a supported feature.

## Prerequisites

1. The Go bridge running and reachable privately from Home Assistant at `rtsp://BRIDGE_HOST:8554`.
2. The actual RTSP camera path (for example `/Front_Door/sd`, as discovered by the Go CLI).
3. HA with access to its live `configuration.yaml` and `custom_components`/`www` folders.
4. A browser supporting Web Audio AudioWorklet, loading HA over HTTPS or a supported localhost context.
5. Camera RTSP backchannel advertising **PCMU/8000** (no arbitrary codec transcoding in the packaged PTT).
6. Optional: [AlexxIT WebRTC Camera](https://github.com/AlexxIT/WebRTC) for video + listening. This is a separate install and is not bundled.

**HA OS:** install/copy into its `/config` directory through a suitable add-on/file share. A stock HA OS appliance is not a Go build host; run the Go bridge on Linux separately.

**HA Container:** the live `/config` is usually mounted from a host folder or Docker volume. Resolve its exact mount before installing; do not use an arbitrary path. Example inspection:

```bash
docker inspect homeassistant --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}'
```

## Step 1 — install files, without a restart

Clone the repository on a computer able to write to the **HA config directory**:

```bash
git clone https://github.com/troianvasile/tuya-ipc-terminal-ptz.git
cd tuya-ipc-terminal-ptz
bash homeassistant/install.sh /path/to/real/ha/config
```

The installer copies:
- `custom_components/little_elf_talk/__init__.py`
- `custom_components/little_elf_talk/rtsp_audio.py`
- `custom_components/little_elf_talk/manifest.json`
- `www/little-elf-ptt-card.js`
- `www/little-elf-talk-processor.js`

Files replaced by the installer are backed up with timestamp suffixes. The script changes **only** the HA config directory you specify. It does **not** change YAML, restart HA, or change the Tuya bridge.

**Existing working installation:** make a separate backup and use a spare HA test instance first. The portable integration is a new implementation, so running this installer on the reference production instance can interrupt its currently working PTT after the next restart.

## Step 2 — configure aliases in Home Assistant

Merge this into your existing `configuration.yaml`; do not delete unrelated integrations:

```yaml
little_elf_talk:
  admin_only: true
  cameras:
    front_door:
      rtsp_url: rtsp://192.168.1.50:8554/Front_Door/sd
    nursery:
      rtsp_url: rtsp://192.168.1.50:8554/Nursery/sd
```

The `rtsp_url` points to the **Go bridge**, not the camera's local IP and not a Tuya cloud host. The HA host/container must be able to connect to this IP and TCP port.

The YAML keys `front_door` / `nursery` are **local aliases**. They need not match the Tuya display name or its path; the Lovelace PTT card uses the alias. Only configured aliases can transmit microphone audio.

`admin_only: true` (default) limits PTT to HA admins. `false` permits any authenticated HA user. Protect the HA account accordingly.

You can use as many aliases as your actual setup supports, but this preview limits concurrent PTT to **one active session per camera** and **four sessions globally**.

## Step 3 — validate HA configuration and restart

Use the HA configuration validation option supported by your installation. Restart Home Assistant **manually** only when ready.

Review HA logs for errors containing `little_elf_talk`, `manifest`, `websocket_api`, `rtsp`. If it does not load, see [troubleshooting](../docs/TROUBLESHOOTING.md#home-assistant-integration-not-loading).

## Step 4 — add one JavaScript Lovelace resource

Register this resource as a **JavaScript module** using the dashboard's resource management UI:

```text
/local/little-elf-ptt-card.js?v=0.1.0
```

The installer also provides the AudioWorklet at `/local/little-elf-talk-processor.js`. **Do not register the processor as a Lovelace card**; the PTT card loads it automatically.

If you see an old frontend after updating, clear browser cache or bump the resource query version and refresh. Both `/local/` paths must return JavaScript, not a 404.

## Step 5 — make a camera card

Use an appropriate Lovelace view and replace the example values:

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

The first card is **video/listening**; the second is the **microphone button**. The example requires the separately installed WebRTC Camera card. If not using it, omit the first card and use the PTT button alone.

For the second camera, use its discovered `rtsp_url` in the video card and its configured local `camera: nursery` for PTT. You can have HA on one host and the Go bridge on another.

## Step 6 — real microphone test

1. Open HA over HTTPS or localhost in Chrome/another supported browser.
2. Allow microphone permission for HA.
3. Open the camera's video, then hold PTT for 3–5 seconds.
4. Speak and listen at the **physical camera speaker**.
5. Release the button. Confirm recording stops and the speaker disarms.
6. Repeat 5–10 times per camera; alternate cameras, navigate away, return, and confirm reconnect.

A UI message or server log saying `speaker enabled` proves a publish was attempted; it does **not** by itself prove physical playback. The Go bridge's MQTT control and outgoing WebRTC audio are separate layers.

## What happens under the hood

```text
Browser mic (HTTPS, permission)
    -> AudioWorklet encodes 160 PCMU bytes per 20ms
    -> Authenticated HA WebSocket (start / chunk / stop, legacy audio accepted)
    -> HA backend RTSP client, separate session per press
    -> RTSP interleaved RTP backchannel
    -> Go bridge Pion WebRTC + Tuya speaker command
    -> Camera speaker
```

No Go PTZ service is required for PTT, and no FFmpeg TTS injection is needed.

## Optional PTZ control from HA

The Go CLI handles multi-region *host selection* through an exact allowlist; its physical PTZ commands are **verified only in EU**. Other regions/cameras may behave differently.

For a separate HA host, optionally run `tuya-ipc-terminal ptz serve` on the bridge host with `LITTLE_ELF_PTZ_TOKEN` (minimum 32 characters). It defaults to `127.0.0.1:8787` and must be placed behind an HTTPS proxy/VPN/private tunnel. See [full guide: PTZ setup](../docs/PORTABLE_HOME_ASSISTANT_SETUP.md#7-optional-ptz-for-home-assistant) and [service example](../examples/tuya-ipc-ptz.service.example).

Merge [`ptz-rest-command.yaml.example`](ptz-rest-command.yaml.example) into the existing HA `rest_command:` block; put the bearer token in `secrets.yaml`. The PTZ REST action uses a **Tuya display name/device ID**, not the local PTT alias.

Example button:

```yaml
type: button
name: Camera left
icon: mdi:chevron-left
tap_action:
  action: perform-action
  perform_action: rest_command.little_elf_ptz
  data:
    camera: Front Door
    direction: LEFT
```

Test the CLI first with a short move, then the optional HTTPS REST helper. The Go PTZ companion is **not enabled or launched by the Home Assistant installer**.

## Security and troubleshooting

- Bridge TCP 8554 is unauthenticated and plaintext. Firewall to HA/go2rtc or private VPN; never publish as an internet service.
- The WebSocket commands require an authenticated HA user; default admin-only; session token is scoped to the same WebSocket connection.
- The frontend should stop recording on release, window blur, visibility change and unmount; backend also has an idle timeout.
- Browser mic requires a secure context/permission and a functioning AudioWorklet.
- Keep Tuya cookies in bridge `.tuya-data/`, never in HA dashboard YAML or this repository.
- For a separate host, use a HA-reachable private RTSP URL; `localhost` points to the HA container itself, not necessarily the Go host.
- No support claim for TTS injection or arbitrary codecs; PCMU/8000 is the target.
- See [`docs/TROUBLESHOOTING.md`](../docs/TROUBLESHOOTING.md) for layer-by-layer checks and safe rollback.

## Source, tests and versioning

```bash
python3 -m compileall -q homeassistant/custom_components/little_elf_talk homeassistant/tests
python3 -m unittest discover -s homeassistant/tests -p 'test_*.py' -v
node --check homeassistant/www/little-elf-ptt-card.js
node --check homeassistant/www/little-elf-talk-processor.js
```

These checks don't simulate HA Core, browsers, real cameras, or a Tuya account. Before describing the portable package as production-ready for third parties, complete a fresh install and physical PTT tests. There is no HACS release/config-flow installer in this repository yet; the install method is **manual YAML + copied custom integration/card**.
