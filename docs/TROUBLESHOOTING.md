# Troubleshooting Tuya IPC RTSP, Home Assistant PTT and PTZ

See [complete installation](PORTABLE_HOME_ASSISTANT_SETUP.md) and the [Home Assistant guide](../homeassistant/README.md). Work **from bridge -> HA network -> HA integration -> microphone -> speaker** and avoid restarting a production bridge until you know which layer failed.

> **Sensitive information:** camera IDs, account addresses, Tuya cookies, saved sessions, PTZ bearer tokens and private network details must be removed from published logs. No TTS/file-injection command is part of the supported setup.

## Bridge does not start / reports "no authenticated users" or "no cameras found"

```bash
pwd
go version
./tuya-ipc-terminal auth list
./tuya-ipc-terminal cameras list
./tuya-ipc-terminal rtsp list-endpoints
```

The app looks for `.tuya-data/` in the **current working directory**, not wherever the executable happens to live. Compare the path, user and executable of the running service:

```bash
systemctl cat tuya-ipc-rtsp.service
systemctl show tuya-ipc-rtsp.service -p ExecStart -p WorkingDirectory -p User --no-pager
journalctl -u tuya-ipc-rtsp.service -n 100 --no-pager
```

If manual auth was run as one user/directory and systemd starts another, fix the service or re-authenticate/discover under the correct account. Protect `.tuya-data/` and do not upload its contents.

## Camera not discovered or authentication expired

```bash
./tuya-ipc-terminal auth show-regions
./tuya-ipc-terminal auth test eu-central user@example.com
./tuya-ipc-terminal cameras refresh
./tuya-ipc-terminal cameras list
```

Replace example region/email with your actual account. The six supported regional web hosts are listed in the [installation guide](PORTABLE_HOME_ASSISTANT_SETUP.md#2-authenticate-to-your-tuya-web-region); this is a host selection feature, **not** a guarantee that every camera/account can authenticate.

If expired, use the CLI's authentication refresh/add flow and verify the selected web region, camera ownership and Tuya app state. Do not commit copied session JSON from other installations.

## RTSP video or listening does not work

Test directly on a trusted client reachable to the bridge:

```bash
ffplay -rtsp_transport tcp rtsp://192.168.1.50:8554/Front_Door/sd
```

Replace address/path. Check TCP 8554, firewall rules, NAT/container routing and whether the bridge has an active camera session. Check the *actual* discovered path; RTSP matching is exact and camera display names can contain spaces.

If SD works but HD doesn't, inspect the individual camera's capabilities; do not advertise HD/H265 as universal. If the host runs HA inside Docker, `127.0.0.1` inside HA might not be the bridge host. The Go RTSP server by default binds all interfaces and must be privately firewalled.

```bash
journalctl -u tuya-ipc-rtsp.service --since "10 minutes ago" --no-pager |
  grep -E 'Starting stream|WebRTC bridge|Failed to start|Stopping|Error|backchannel'
```

Avoid filtering so aggressively that you hide the first error.

## Home Assistant integration not loading

Confirm the actual HA `/config` contains:

```text
custom_components/little_elf_talk/__init__.py
custom_components/little_elf_talk/manifest.json
custom_components/little_elf_talk/rtsp_audio.py
www/little-elf-ptt-card.js
www/little-elf-talk-processor.js
```

Check your YAML indentation and that the top-level `little_elf_talk:` has `cameras:` with at least one alias and a valid `rtsp_url:`. Validate HA config before restarting. Browser dashboard YAML alone does **not** load the backend. Use the HA log to find the exact error.

This is a manual YAML custom integration, not a HACS/config-flow package at present.

## No PTT button or frontend errors

- Register `/local/little-elf-ptt-card.js?v=0.1.0` as a **JavaScript module** Lovelace resource.
- Do **not** register `little-elf-talk-processor.js` as a second dashboard resource. The card loads it from `/local/little-elf-talk-processor.js`.
- Use a current browser over **HTTPS or localhost**. Check the browser's microphone permission.
- If HTTP 404/old card version occurs, confirm the files are in HA's real `/config/www` and refresh frontend cache/resource version.
- Ensure an AudioWorklet-capable browser; a microphone light alone does not prove packets reached RTSP.

## PTT button operates but the camera speaker is silent

**First establish whether video/listening works.** Then attempt a normal 3–5-second microphone press, no TTS injection. Watch the Go journal:

```bash
journalctl -fu tuya-ipc-rtsp.service -o cat |
  grep --line-buffered -E 'Talkback:|backchannel|WebRTC bridge|Failed to start|error'
```

Possible layers:

| Observation | Likely next check |
| --- | --- |
| No RTSP backchannel connection / no speaker messages | HA WebSocket integration/configured alias, HA-to-bridge TCP, browser microphone permissions |
| RTSP backchannel setup but no speaker enable | RTP packets arriving / codec PCMU/8000 / RTSP sender |
| Speaker enable/disable messages, physical speaker silent | Outgoing WebRTC track, camera speaker state, Tuya command acceptance, codec negotiation |
| Works after restarting Go bridge but fails after viewer disconnect | Inspect idle shutdown and whether all viewers actually released RTSP clients |
| Only TTS injection is silent | TTS is **not supported or validated**; don't modify working live PTT to debug it |

A `Talkback: speaker enabled` message means the command publish path succeeded locally, **not** that the physical device played audio.

On a new install test multiple presses, alternate cameras and close/reopen all viewers to exercise idle cleanup. If only one camera fails, preserve the working camera while investigating.

## HA PTT camera alias vs. PTZ camera name

The names are intentionally different:

```yaml
# HA configuration.yaml:
little_elf_talk:
  cameras:
    baby_room:
      rtsp_url: rtsp://192.168.1.50:8554/Baby_Room/sd

# Lovelace PTT:
type: custom:little-elf-ptt-card
camera: baby_room
```

**PTZ** `rest_command.little_elf_ptz` expects the Tuya **display name** or device ID, for example `Baby Room`. The bridge stream path uses the discovered RTSP path, often underscored. Do not assume these three IDs are interchangeable.

## PTZ CLI works but Home Assistant button fails

Confirm the cloud CLI works in the same directory as authenticated sessions:

```bash
./tuya-ipc-terminal ptz move --camera "Front Door" --direction LEFT --duration 400ms
```

The optional PTZ companion is a **second process** with token authentication, started explicitly. Check:

```bash
systemctl status tuya-ipc-ptz.service --no-pager
journalctl -u tuya-ipc-ptz.service -n 60 --no-pager
```

If you did not install systemd for PTZ, use the foreground process and its local logs. It defaults to `127.0.0.1:8787`, which HA on another host cannot access directly. Use an HTTPS reverse proxy/VPN/tunnel; never move a bearer token through plaintext public HTTP.

In HA, the REST command uses `Authorization: !secret little_elf_ptz_authorization`; the secrets value includes the `Bearer ` prefix. The expected JSON includes `camera`, `direction` (uppercase) and `duration_ms` (100–1500). Wrong token returns HTTP 401; unsupported direction/duration gives HTTP 400. The Cloud API may still reject a valid request, especially in an **untested region**.

## Update / rollback when production is working

Before changing production:

```bash
systemctl cat tuya-ipc-rtsp.service
systemctl show tuya-ipc-rtsp.service -p MainPID -p ExecStart --no-pager
```

Build new Go binaries under a different filename, verify tests, and preserve the previous binary and service unit. Change the service deliberately during a maintenance window. A temporary override under `/run/systemd/system` does **not** survive reboot.

For HA, back up `configuration.yaml`, existing `custom_components/little_elf_talk` and both `www/little-elf-*.js` files. The installer makes timestamp backups but **does not** edit YAML or restart HA. Restore files/config and restart HA to roll back. The portable backend has not yet passed an independent fresh-install test; do not replace a known-good private instance casually.

## When reporting an issue

Provide (after sanitization): Go revision/`go version`, OS, HA version/install type, PTT browser, camera skill/codec **without identifying IDs**, RTSP endpoint shape (redacted), exact error and whether video/listening work. Do not post cookies, camera device ID, session key, QR code or bearer token.
