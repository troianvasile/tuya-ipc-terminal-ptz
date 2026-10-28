# Little Elf RTSP + Home Assistant PTT (portable preview)

This folder packages a **new portable implementation** of Home Assistant push-to-talk for the Go Tuya IPC bridge.

**Status: preview, not yet validated on a clean Home Assistant instance.** It is not the same source as the already-tested private installation. Test on a spare HA system before replacing the working installation. No TTS support is promised.

## Requirements

- Home Assistant with a working custom integration directory (YAML mode supported)
- HTTPS Home Assistant frontend (or localhost) with microphone permissions
- Browser with `AudioWorklet` support
- A running Go bridge from the `feat/portable-ha-multiregion` branch
- A Tuya camera whose **SD RTSP backchannel advertises PCMU/8000** (other codecs are not yet supported by this sender)
- TCP connectivity **from Home Assistant itself** to the Go RTSP bridge
- Optional: AlexxIT WebRTC Camera custom Lovelace card for video and listening

The microphone path does **not** depend on FFmpeg, a go2rtc TTS push endpoint, or the Home Assistant instance being in Docker. go2rtc/WebRTC Camera remains a convenient separate video player.

## Install

1. Clone the repository on a computer that has access to the Home Assistant config directory:

   ```sh
   git clone --branch feat/portable-ha-multiregion --single-branch \
     https://github.com/troianvasile/tuya-ipc-terminal-ptz.git
   cd tuya-ipc-terminal-ptz
   bash homeassistant/install.sh /path/to/homeassistant/config
   ```

   For Docker installations, `/path/to/homeassistant/config` is the **host directory mounted as `/config`**. The installer changes only files and creates backups. Alternatively copy `custom_components/little_elf_talk/` and `www/little-elf-ptt-card.js` manually.

2. Add the configuration from `configuration.yaml.example` to your existing `configuration.yaml`; change the **HA-reachable** RTSP bridge host and the discovered camera path:

   ```yaml
   little_elf_talk:
     admin_only: true
     cameras:
       nursery:
         rtsp_url: rtsp://192.168.1.50:8554/Nursery/sd
   ```

   `nursery` is a local alias: it is **not necessarily the Tuya camera display name**. Only camera IDs listed in YAML can receive microphone audio. `admin_only: true` means only HA admin users can use PTT; set `false` explicitly to allow any HA authenticated user.

3. Restart Home Assistant **after checking its YAML configuration**. The installer does not do this.

4. In Home Assistant, add a Lovelace **JavaScript resource** at `/local/little-elf-ptt-card.js?v=0.1.0` with type `JavaScript module`. Clear frontend caches or bump the query version if necessary.

5. Add the card inside a view:

   ```yaml
   type: vertical-stack
   cards:
     - type: custom:webrtc-camera
       url: rtsp://192.168.1.50:8554/Nursery/sd
       mode: mse,hls
       media: video,audio
       ui: true
     - type: custom:little-elf-ptt-card
       camera: nursery
   ```

   If WebRTC Camera is not installed, omit the video card; the PTT card can still be configured separately. For its own video rendering, use the **address reachable from HA/go2rtc**, not a Docker `172.17.0.1` gateway borrowed from another installation.

6. Open from an HTTPS browser, permit microphone access, hold PTT for 3-5 seconds and release. Test reconnects and try multiple camera aliases. Do **not** inject TTS test audio into this portable preview.

## Architecture

```text
[Browser HTTPS/microphone]
       -> [AudioWorklet resamples to 8 kHz PCMU]
       -> [HA authenticated WebSocket: little_elf_talk/{start,chunk,stop}]
       -> [HA backend TCP RTSP SETUP backchannel (interleaved channel 4)]
       -> [Go Tuya bridge: RTP -> WebRTC -> camera speaker]
```

Video and listening use a separate RTSP reader and do not need the microphone card to hold an open microphone connection.

## Security and lifecycle

- No WebSocket bearer tokens, Tuya credentials, camera IDs, or IP addresses are committed.
- By default PTT is limited to **HA admin users**; all commands require the same authenticated HA WebSocket that created the session.
- The backend accepts camera aliases configured in YAML; the frontend cannot choose arbitrary RTSP addresses.
- Mic is stopped on pointer release, blur, visibility change and card unmount. Backend sessions are cleared on WebSocket drop or 5 seconds of audio inactivity.
- Each camera accepts one PTT session at a time; global maximum four active sessions.
- RTSP traffic on port 8554 is **not authenticated or encrypted** by the Go bridge. Keep it on LAN/VPN and firewall it. Do not publicly expose it.
- Session storage for the Go Tuya bridge remains in `.tuya-data/`, not in Home Assistant.

## Multi-region PTZ status

Go PTZ now accepts authenticated sessions for all six web hostnames in the project's available-region list: `eu-central`, `eu-east`, `us-west`, `us-east`, `china`, `india`. Hostnames are checked against an exact allowlist, so tokens/cookies cannot be forwarded to arbitrary URLs.

**PTZ is physically confirmed on two EU cameras only.** Other regions must be physically tested. For Home Assistant on another host, an **optional** Go companion `ptz serve` exposes the PTZ CLI through a bearer-token-protected HTTP endpoint (disabled unless started explicitly). See [`../examples/tuya-ipc-ptz.service.example`](../examples/tuya-ipc-ptz.service.example) and [`ptz-rest-command.yaml.example`](ptz-rest-command.yaml.example). The latter defines the same `rest_command.little_elf_ptz` action used by the reference dashboard, with camera name and direction as inputs. Keep the companion bound to localhost behind HTTPS/VPN for remote HA, never openly exposed over HTTP. The browser PTT path and PTZ remain independent.

## Build/verification

```sh
go test ./...
python3 -m compileall -q homeassistant/custom_components/little_elf_talk homeassistant/tests
python3 -m unittest discover -s homeassistant/tests -p 'test_*.py' -v
node --check homeassistant/www/little-elf-ptt-card.js
```

The standalone RTSP tests mock the TCP bridge. They do **not** prove real camera audio, HA WebSocket compatibility, Tuya region portability, or browser capture on an arbitrary platform. A second clean HA installation is required for release acceptance.
