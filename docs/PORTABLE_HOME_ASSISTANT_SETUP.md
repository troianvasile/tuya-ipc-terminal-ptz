# Complete installation: Tuya bridge + Home Assistant two-way audio + optional PTZ

This is the **start-to-finish guide for a new setup**, using the default GitHub `main` branch. Use the [root README](../README.md) for a short overview, [HA-specific guide](../homeassistant/README.md) for configuration details, and [troubleshooting](TROUBLESHOOTING.md) when anything fails.

> **Compatibility:** The Go bridge was validated with two Little Elf cameras. The *newly packaged* HA backend/card and PTZ companion pass automated tests but **require live verification** on a clean HA installation before being called broadly supported. PCMU/8000 talkback is required for the bundled HA microphone sender. PTZ is physically confirmed only in the EU, despite explicit support for six vendor web hosts. TTS is not supported.

## Before you begin: three addresses you must distinguish

| Value | Purpose | Example |
| --- | --- | --- |
| `BRIDGE_HOST` | Linux server running the Go bridge; HA must reach TCP 8554 on this address | `192.168.1.50` |
| `CAMERA_RTSP_PATH` | Exact path discovered by Go camera registry; typically spaces become underscores | `Front_Door` |
| `CAMERA_ALIAS` | HA-local key for PTT, freely chosen and used in the card | `front_door` |

PTZ uses the **Tuya display name or device ID**, not the PTT alias. Neither `localhost` nor Docker gateway `172.17.0.1` should be copied blindly between machines.

## 1. Choose where the Go bridge runs

Use a regular Linux host/VM with a persistent filesystem and outbound internet access for Tuya. Home Assistant may live on the **same host** or a **different** one. HA OS users normally run the Go bridge on a separate Linux host; the project does not ship a Supervisor add-on or bridge Docker image yet.

Install Git and a supported **Go 1.23+** toolchain. The repository currently specifies `toolchain go1.23.9` in `go.mod`; the Go command may download this toolchain automatically. On offline or restricted hosts, install Go 1.23.9 or newer manually. Check, rather than assuming your distro's `apt` version is recent enough:

```bash
git --version
go version
```

From a terminal **as the account that will operate the bridge**:

```bash
git clone https://github.com/troianvasile/tuya-ipc-terminal-ptz.git
cd tuya-ipc-terminal-ptz
go test ./...
go build -o tuya-ipc-terminal .
./tuya-ipc-terminal --help
```

Record the **absolute path** printed by `pwd`. Use it consistently for authentication, discovery and service `WorkingDirectory`.

## 2. Authenticate to your Tuya web region

List the built-in regions:

```bash
./tuya-ipc-terminal auth show-regions
```

| Region key | Host |
| --- | --- |
| `eu-central` | `protect-eu.ismartlife.me` |
| `eu-east` | `protect-we.ismartlife.me` |
| `us-west` | `protect-us.ismartlife.me` |
| `us-east` | `protect-ue.ismartlife.me` |
| `china` | `protect.ismartlife.me` |
| `india` | `protect-in.ismartlife.me` |

Replace region/email with your **own** values. QR login (default) requires interaction with the Tuya/compatible app; password is an alternate interactive flow:

```bash
./tuya-ipc-terminal auth add eu-central user@example.com
# Alternative:
# ./tuya-ipc-terminal auth add eu-central user@example.com --password

./tuya-ipc-terminal auth list
./tuya-ipc-terminal auth test eu-central user@example.com
```

Do **not** put a password on the process command line or into a committed script. The account's session and camera registry are stored in `.tuya-data/` in this directory; keep that directory private and back it up securely.

## 3. Discover cameras and RTSP paths

```bash
./tuya-ipc-terminal cameras refresh
./tuya-ipc-terminal cameras list
./tuya-ipc-terminal rtsp list-endpoints
```

If necessary, inspect a camera:

```bash
./tuya-ipc-terminal cameras info "Front Door"
```

A display name like `Front Door` often has RTSP path `/Front_Door`. Do not assume the case or punctuation; the authoritative path is the one discovered by this instance.

## 4. Verify the RTSP bridge *before* Home Assistant

Run it interactively first:

```bash
./tuya-ipc-terminal rtsp start --port 8554
```

Keep that terminal open. From a **different** terminal/client able to reach the bridge (replace the host and path):

```bash
ffplay -rtsp_transport tcp rtsp://192.168.1.50:8554/Front_Door/sd
```

You can also test with a trusted RTSP-compatible player if `ffplay` is absent. Confirm video **and incoming camera audio**. Use `/hd` only if the particular camera advertises and supports it.

Exit the foreground server with Ctrl+C before installing systemd.

### Port / firewall

The Go RTSP listener currently binds `:8554` (all interfaces). Only allow the HA/go2rtc client private IP(s) or VPN network to reach TCP 8554. **Do not forward TCP 8554 on your internet router or publish the RTSP feed publicly**: the bridge has no RTSP authentication or TLS.

## 5. Make the bridge persistent with systemd (Linux)

Open [the service template](../examples/tuya-ipc-rtsp.service.example). Replace **both** `INSTALL_DIR` with the full `pwd` path and `SERVICE_USER` with the Linux account that performed authentication. For example, if you installed in `/home/cameras/tuya-ipc-terminal-ptz` under user `cameras`:

```ini
[Unit]
Description=Tuya IPC RTSP / two-way audio bridge
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=cameras
WorkingDirectory=/home/cameras/tuya-ipc-terminal-ptz
ExecStart=/home/cameras/tuya-ipc-terminal-ptz/tuya-ipc-terminal rtsp start --port 8554
Restart=always
RestartSec=10
TimeoutStopSec=10
KillMode=control-group
NoNewPrivileges=true
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

Save this as `/etc/systemd/system/tuya-ipc-rtsp.service`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tuya-ipc-rtsp.service
sudo systemctl is-active tuya-ipc-rtsp.service
sudo systemctl status tuya-ipc-rtsp.service --no-pager
sudo journalctl -u tuya-ipc-rtsp.service -n 80 --no-pager
```

**Critical:** using root for manual authentication and a different `User`/`WorkingDirectory` in systemd will make the camera registry appear empty. Re-run authentication and discovery under the service account/directory or correct the unit.

For an existing production bridge, do **not** blindly replace its unit or restart it. Back up the existing file, check its actual executable (`systemctl show ... -p ExecStart`), and roll out after a scheduled test.

## 6. Connect Home Assistant to the bridge

### 6A. Find the Home Assistant configuration folder

- **Home Assistant Container:** identify the host bind mount mapped to `/config` (e.g. via `docker inspect homeassistant`), then use that **host path** as installer target.
- **Home Assistant OS:** the configuration folder is `/config` inside an appropriate terminal/editor add-on. If the add-on has no Git, clone/download the repository on another machine and copy `homeassistant/custom_components/little_elf_talk/` and `homeassistant/www/` into `/config` with a file editor, Samba or SCP workflow.
- **Home Assistant Core (venv):** use the directory containing the active `configuration.yaml`.

Never run the installer against an empty directory unrelated to the active HA instance.

### 6B. Install the integration and two JavaScript files

From the repository clone on a system that can write to the HA config folder:

```bash
bash homeassistant/install.sh /path/to/actual/ha/config
```

This copies:
- `custom_components/little_elf_talk/__init__.py`, `manifest.json` and `rtsp_audio.py`.
- `www/little-elf-ptt-card.js` and `www/little-elf-talk-processor.js`.

It creates backups when replacing older files. It **does not** restart HA, edit YAML or change the Go bridge.

If an earlier private version of the integration is already in use, **do not overwrite it in production for a first test**; use a spare HA instance or preserve your original files and rollback plan. This portable version is a **new** implementation.

### 6C. Configure PTT camera aliases

Merge into the existing `configuration.yaml` (do not replace unrelated configuration):

```yaml
little_elf_talk:
  admin_only: true
  cameras:
    front_door:
      rtsp_url: rtsp://192.168.1.50:8554/Front_Door/sd
    nursery:
      rtsp_url: rtsp://192.168.1.50:8554/Nursery/sd
```

Use the **address reachable from the HA process/container**, not just from your personal laptop. Test connectivity from inside HA's network namespace where possible. Camera keys (`front_door`, `nursery`) are private aliases you select for PTT; they must match the Lovelace card's `camera` property.

By default `admin_only: true` limits PTT to HA administrator accounts. Set `false` only if you deliberately want any authenticated HA user to speak through the camera.

### 6D. Validate configuration and restart HA

Use HA's configuration validation mechanism for your installation, then restart HA **manually**. For Home Assistant Container, the service container must be restarted (only after validation and at a convenient time). Check HA logs for `little_elf_talk` import, manifest, configuration or WebSocket registration errors.

### 6E. Install the Lovelace resource

In Home Assistant's dashboard **resource management** (menu location varies by dashboard/HA version), register the JavaScript module URL:

```text
/local/little-elf-ptt-card.js?v=0.1.0
```

The separate `little-elf-talk-processor.js` must exist at `/local/little-elf-talk-processor.js`; it is loaded by the card, not registered as a second Lovelace card.

Install the [AlexxIT WebRTC Camera custom integration/card](https://github.com/AlexxIT/WebRTC) separately for video/listening; check that the HA/go2rtc instance can reach your RTSP server. The PTT backend is independent of go2rtc's TTS injection API.

### 6F. Create the Lovelace card

Add the following to a Lovelace view (after adjusting IP/path/alias):

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

Open HA using HTTPS (or localhost in a supported browser), allow microphone permission, hold the PTT button for 3–5 seconds, and release. Confirm sound **from the physical camera speaker**, not from the web player. Test 5–10 times and verify it stops when you release/leave the page.

If you only want PTT, omit the WebRTC video card; if you use only the video card, it does **not** provide this project's browser PTT by itself.

## 7. Optional PTZ for Home Assistant

### 7A. First confirm PTZ works through Go CLI

From the same bridge install directory, short movement first:

```bash
./tuya-ipc-terminal ptz move --camera "Front Door" --direction LEFT --duration 400ms
./tuya-ipc-terminal ptz stop --camera "Front Door"
```

PTZ was physically tested only with two EU devices. Non-EU region hosts are allowed in code, but are **not physically verified**. The cloud PTZ request can fail if the API or model differs. Never direct a camera into an obstruction.

### 7B. Optional companion service, disabled by default

The PTZ HTTP server is a **separate process** and never required for RTSP/PTT. Generate a long random bearer token, store it outside Git, then run:

```bash
# On bridge Linux host:
TOKEN="$(openssl rand -hex 24)"
sudo install -m 0600 /dev/null /etc/little-elf-ptz.env
printf 'LITTLE_ELF_PTZ_TOKEN=%s\n' "$TOKEN" | sudo tee /etc/little-elf-ptz.env >/dev/null

# In the bridge working directory, start a temporary foreground trial:
LITTLE_ELF_PTZ_TOKEN="$TOKEN" ./tuya-ipc-terminal ptz serve --listen 127.0.0.1:8787
```

From **another** terminal on the same bridge host:

```bash
curl --fail-with-body -sS \
  -H "Authorization: Bearer YOUR_TOKEN_FROM_ABOVE" \
  -H "Content-Type: application/json" \
  -d '{"camera":"Front Door","direction":"LEFT","duration_ms":400}' \
  http://127.0.0.1:8787/api/ptz/move
```

This endpoint permits only POST `/api/ptz/move` with short durations (100–1500 ms) and supported directions. Stop the foreground service before enabling the persistent [PTZ systemd companion template](../examples/tuya-ipc-ptz.service.example), replacing user and install directory.

**For HA on a different host:** `127.0.0.1` on the bridge is **not reachable directly from HA**. Set up an authenticated HTTPS reverse proxy, VPN-protected tunnel or equivalent private transport **before** changing HA's REST URL. Do not bind the PTZ companion to `0.0.0.0` on a public interface or send the bearer token over an unencrypted public link.

### 7C. Home Assistant PTZ command / button

Take [`homeassistant/ptz-rest-command.yaml.example`](../homeassistant/ptz-rest-command.yaml.example) and merge its `rest_command:` into `configuration.yaml`. Configure its `url` to your **working, HTTPS/private** PTZ address (including reverse-proxy routing), and in `secrets.yaml` provide:

```yaml
little_elf_ptz_authorization: "Bearer PUT_THE_SAME_RANDOM_TOKEN_HERE"
```

Example action from a Lovelace button:

```yaml
type: button
name: Turn camera left
icon: mdi:chevron-left
tap_action:
  action: perform-action
  perform_action: rest_command.little_elf_ptz
  data:
    camera: Front Door
    direction: LEFT
```

PTZ REST `camera` refers to the **Tuya display name or device ID**, whereas the PTT card `camera` refers to the HA alias.

## 8. Validation checklist

- [ ] Go bridge builds and `go test ./...` passes.
- [ ] Regional auth succeeds; sessions/camera registry persist after process restart.
- [ ] SD video and incoming camera sound work from a second RTSP client.
- [ ] HA/go2rtc reaches bridge TCP 8554 on private IP/VPN.
- [ ] HA YAML validates, integration initializes, Lovelace PTT/processor files load.
- [ ] Camera physically plays 5–10 consecutive PTT attempts; release actually mutes.
- [ ] Test with two cameras, alternate PTT and video sessions.
- [ ] Close all viewers, allow idle shutdown, reopen and verify audio still works.
- [ ] Restart each service *deliberately* and verify reconnection; eventually verify post-reboot.
- [ ] RTSP private firewall, cookies/keys protected, no exposed PTZ HTTP.
- [ ] If PTZ enabled, short movement and STOP work using your own region/device.

## 9. Updating and rollback

**Go:** Keep the previous executable and a copy of any systemd override. In a dedicated clone, `git pull --ff-only`, `go test ./...`, build a separate output, then make a deliberate service change and verify. Never edit/overwrite a running known-good binary or assume a developer's `/run/systemd/system` test override will survive reboot.

**Home Assistant:** Save a copy of `configuration.yaml`, previous `custom_components/little_elf_talk/` and the two `www/*.js` files. The installer backs up files and the old integration directory with a timestamp suffix. To revert, restore those files and YAML, clear frontend caches and restart HA deliberately.

**PTZ:** Disable the separate PTZ companion service if needed. RTSP/PTT continues independently. Rotate any exposed token in both bridge environment and HA secrets.

See [troubleshooting](TROUBLESHOOTING.md) for specific failures and diagnostic commands.

## Security and scope notes

This project relies on Tuya cloud signalling and reverse-engineered interfaces. RTSP is plaintext/unauthenticated. Only use it for devices/accounts you administer. Browser/WebSocket auth doesn't protect an externally exposed RTSP port. Multi-region host validation prevents sending session cookies to arbitrary hostnames; it does not guarantee the vendor PTZ API works in all regions. Any logs shared publicly must be sanitized.
