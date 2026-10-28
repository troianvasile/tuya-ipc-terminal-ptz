# Portable Home Assistant installation: current status and guide

> **Status: portable Home Assistant PTT integration is now included under `homeassistant/` as an UNVALIDATED preview.** The working private HA prototype is not automatically overwritten; validate on a spare HA instance before a release.
> The validated Go source is on the `fix/ptt-rearm-sd-lifecycle` branch. Do not claim turnkey or universal device support until the HA components are added and a clean-room installation passes.

## Validated in the reference installation (2026-10-28)

- Two Little Elf / Tuya cameras, using `/sd` H264 RTSP streams and PCMU/8000 talkback.
- Video and listening through a Home Assistant `custom:webrtc-camera` card, `mode: mse,hls`.
- Browser microphone PTT through a **separate custom Home Assistant integration and card**, installed outside this Git repository.
- Repeated live PTT on both cameras, including after attempting the currently nonfunctional experimental TTS injection.
- Go fixes for SD handshake, concurrent stream startup, speaker rearm, outgoing RTP continuity across RTSP senders, and idle WebRTC shutdown.

These tests **do not** establish that all Tuya models, firmware versions, regions, codecs, or browser/HA versions work.

## What is in this Git repository

- `pkg/rtsp/`: Go RTSP streaming, RTSP audio backchannel, speaker lifecycle and RTP continuity.
- `cmd/auth/`, `cmd/cameras/`: Tuya authentication and camera discovery.
- `cmd/ptz/`: optional PTZ CLI. **Its current implementation explicitly requires the EU server `protect-eu.ismartlife.me`**, so don't describe PTZ as multi-region.
- Tests for talkback and WebRTC idle shutdown.

## Portable Home Assistant preview

This branch now includes:
- `homeassistant/custom_components/little_elf_talk/`: YAML-configured authenticated WebSocket sender and async RTSP PCMU backchannel.
- `homeassistant/www/little-elf-ptt-card.js`: browser push-to-talk capture using AudioWorklet.
- `homeassistant/install.sh`: file-only installer with automatic backups.
- `homeassistant/configuration.yaml.example`, `homeassistant/lovelace.yaml.example`: generic HA config and cards.
- `homeassistant/ptz-rest-command.yaml.example`: optional PTZ dashboard action.
- `examples/tuya-ipc-ptz.service.example`: separately launched bearer-token protected HTTP PTZ companion, default loopback.
- CI and isolated RTSP tests.

**Start with [homeassistant/README.md](../homeassistant/README.md).** This is a new portable implementation and has not yet passed live testing on a second HA installation. Other Tuya models and non-EU PTZ remain unverified.

## Remaining release checks

1. Fresh-install HA test and browser microphone PTT on multiple cameras.
2. Confirm WebSocket compatibility against the original private prototype.
3. Test PTZ HTTPS/VPN companion from another HA host.
4. Physically validate PTZ in other authenticated Tuya regions.
5. Confirm secret protection, firewall isolation and no credentials in Git.

## Reproducible Go bridge installation (separate Linux machine or HA host)

1. Install Go **1.23 or newer** (see `go.mod`; current toolchain in repository: `go1.23.9`). Use Git for checkout.
2. Check out the tested branch, compile and test:

   ```sh
   git clone --branch fix/ptt-rearm-sd-lifecycle --single-branch \
     https://github.com/troianvasile/tuya-ipc-terminal-ptz.git
   cd tuya-ipc-terminal-ptz
   go test ./pkg/rtsp ./pkg/webrtc
   go build -o tuya-ipc-terminal .
   ```

3. Run the authentication, discovery, and server **as the same OS user and from the same working directory**:

   ```sh
   ./tuya-ipc-terminal auth add eu-central user@example.com
   ./tuya-ipc-terminal cameras refresh
   ./tuya-ipc-terminal cameras list
   ./tuya-ipc-terminal rtsp start --port 8554
   ```

   Choose the actual account region instead of the example `eu-central`. User sessions and the camera registry are saved in `<working-directory>/.tuya-data/`; keep it private (directory mode 0700 and files 0600). **Do not assume a service started with a different WorkingDirectory or User can find the sessions.**

4. The RTSP path comes from camera discovery. Spaces are replaced with underscores by `GenerateRTSPPath`. For example, a camera named `Front Door` normally maps to `/Front_Door`. Confirm the actual `RTSPPath` in discovery data.

   ```text
   rtsp://<BRIDGE_HOST>:8554/Front_Door/sd
   ```

5. For systemd use the generic `examples/tuya-ipc-rtsp.service.example`. Replace its install directory and service user; put the credentials/registry in the configured working directory. Test restart and boot persistence on the target server.

**Network security:** the Go listener binds on all addresses (`:<port>`) by default. Restrict TCP 8554 using a firewall/VPN or private network; do **not** expose an unauthenticated RTSP endpoint to the public internet.

## Home Assistant network and viewing

- Configure Home Assistant/go2rtc to reach `<BRIDGE_HOST>:8554` **from inside the Home Assistant/container network**; do not copy Docker gateway IP `172.17.0.1` from another machine.
- Add the camera stream to your Home Assistant go2rtc instance as needed; example: `examples/go2rtc.yaml.example`.
- Video/listening can be rendered through the separately installed `custom:webrtc-camera` card using `mode: mse,hls`. See `examples/lovelace-little-elf.yaml.example`.
- The PTT card requires installation of the HA custom integration and JavaScript card from the `homeassistant/` directory; do not expect a standard HA RTSP camera to provide microphone talkback on its own.
- For a camera whose displayed name is `Baby Room` but its RTSP path is `/Baby_Room`, the HA PTT identifier in the reference setup follows the RTSP path without the leading slash, while the PTZ CLI resolves the **displayed name or device ID**. A packaged HA integration must define and validate this mapping explicitly.
- Browser microphone capture generally requires a secure browser context (HTTPS or localhost) and microphone permission; verify actual support in each target browser.
- The current HA PTT prototype uses a Home Assistant WebSocket pipeline and go2rtc audio backchannel. It is **not** supplied by simply enabling generic Home Assistant RTSP cameras.

## Tests before declaring another installation supported

- Login, camera discovery, PTZ CLI if available for that region.
- Fresh start + five reconnects of `/sd`, and test `/hd` separately if supported.
- Live video and listening from the target Home Assistant environment.
- Five to ten browser microphone PTT attempts per camera, alternating between cameras.
- Close all RTSP clients, wait beyond the configured idle delay, verify the Go bridge actually logs shutdown and a new viewer starts a fresh bridge.
- Reboot/restart bridge + Home Assistant; verify state, service paths and streaming.
- Confirm firewall isolation, no plaintext secrets in logs or repository.
- Treat TTS/file injection as **experimental and not validated**, even if ordinary PTT works.

## Known limitations and caveats

- Tested on two Little Elf devices; other Tuya camera models may require changes to SDP, audio negotiation or the speaker MQTT command.
- Current talkback RTP rewrite assumes PCMU/8000 one-byte samples for timestamp progression; other codecs need explicit codec-aware handling before promising two-way talk.
- PTZ API is reverse engineered and EU-host restricted in `cmd/ptz/ptz.go`.
- The existing README's general two-way-audio feature statements describe Go capability, **not a completed HA integration package**.
- TTS file injection is not proven to produce audible camera playback. Do not advertise it as supported.
