# Supervisor-free Tuya IPC Bridge — first-time setup

**Status: experimental / draft PR.** Do not overwrite a working camera bridge or Home Assistant installation. This package has not yet been verified on a clean machine with a physical camera.

This is the **standalone Docker Compose** option for a Linux host. It works independently of Home Assistant Supervisor, whether Home Assistant runs in Docker, on HA OS, or on another machine. It bundles the existing Go RTSP bridge and an authenticated QR-login UI. **PTT in Home Assistant is a separate installation step**; the optional PTZ service is not started by this Compose setup.

## 0. Before you install

You need a Linux computer/VPS with Docker Engine, the `docker compose` plugin, Git, outbound access to the Tuya service and cameras, and at least one supported Tuya/Smart Life or Little Elf account.

> **Networking:** Tuya signalling is cloud based; the bridge host needs outbound network connectivity. RTSP is **not encrypted or authenticated**. Keep TCP 8554 private. For HA on another machine use a VPN/private LAN and firewall the port to only trusted hosts. If the camera is behind NAT and WebRTC cannot negotiate, no amount of RTSP port forwarding fixes the camera side.

Check prerequisites:

```sh
docker --version
docker compose version
git --version
ss -ltn | grep -E ':(8554|8788)\b' || true
```

If port 8554 is in use (for example, by your existing systemd Tuya bridge), **do not start this Compose deployment on that same address/port**. Use a spare host or test VM. The default port 8788 on the host is for the local Web UI; it must also be free.

## 1. Get the experimental branch

```sh
git clone --branch feature/supervisor-free-tuya-bridge https://github.com/troianvasile/tuya-ipc-terminal-ptz.git
cd tuya-ipc-terminal-ptz/deploy
cp .env.example .env
```

Generate a random password and edit `.env`:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
nano .env
chmod 600 .env
```

Set `WEB_USERNAME` and paste the random password into `WEB_PASSWORD` (at least 20 characters). Do not commit `.env` or paste it into logs/issues.

**Connecting to RTSP:** `RTSP_BIND_IP=127.0.0.1` is intentionally localhost-only. For remote HA, set it to the **trusted VPN/LAN IP of the bridge host** (for example `10.8.0.5`) and allow inbound TCP 8554 only from the Home Assistant host. Never use `0.0.0.0` on an internet-exposed VPS.

For optional Home Assistant notifications, set `HA_URL` to the HA base URL reachable **from inside Docker** (e.g. `http://192.168.1.20:8123`) and `HA_TOKEN` to a HA long-lived access token. Both fields can be empty. These are **only** for notification delivery: the RTSP bridge and QR UI work without them.

## 2. Build and start

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=60
```

On first install the Go binary is built inside Docker. Your system's Go version is not used. The bridge runs as a non-root user and stores session credentials in the persistent named volume `tuya_data`.

## 3. Log in through the private browser UI

On your **own computer**, create an SSH tunnel to the bridge Linux host:

```sh
ssh -L 8788:127.0.0.1:8788 USER@BRIDGE_HOST
```

Keep that terminal open and visit **http://127.0.0.1:8788/** on the same computer. Your browser asks for the `WEB_USERNAME` and `WEB_PASSWORD` from `.env`.

In the UI, select one of `eu-central`, `eu-east`, `us-west`, `us-east`, `china` or `india` and enter the account email. Select **Start QR login**. Open Tuya Smart / Smart Life (or your camera's compatible Tuya-variant app), use its built-in QR scanner from the profile/account screen, and scan the code. **Your phone's normal camera QR scanner will not work.**

A successful login stores a session, refreshes cameras, and starts RTSP automatically. If scanning fails, confirm that the app account and region are correct and try a fresh QR code. Existing accounts can be reauthenticated through the same flow.

**Current limitation:** this preview provides QR login only; password login, account deletion and account-management improvements are not yet built into the browser UI. Use the Go CLI when necessary.

## 4. Discover your camera's exact stream path

```sh
docker compose exec tuya-bridge tuya-ipc-terminal auth list
docker compose exec tuya-bridge tuya-ipc-terminal cameras refresh
docker compose exec tuya-bridge tuya-ipc-terminal cameras list
docker compose exec tuya-bridge tuya-ipc-terminal rtsp list-endpoints
```

Copy the **actual** discovered camera RTSP path; never assume that the display name is the URL path. Test from a machine allowed to reach RTSP using VLC or ffplay, for example:

```sh
ffplay -rtsp_transport tcp 'rtsp://BRIDGE_VPN_IP:8554/Your_Camera/sd'
```

`/sd` versus `/hd` and audio codec support depend on each model.

## 5. Home Assistant Container, HA OS and other deployments

**Video only:** Add the RTSP stream using your HA camera integration or go2rtc. From an HA Docker container, `localhost` points to the HA container, **not** the bridge. Use the bridge's reachable LAN/VPN IP.

**Browser microphone → camera speaker (PTT):** Install the separate custom HA integration/card from [homeassistant/README.md](../homeassistant/README.md). For HA Docker, inspect the real `/config` host mount; do **not** install inside a disposable container layer. The card needs an HTTPS browser context, HA authentication and a compatible PCMU/8000 backchannel.

**PTZ:** The Go CLI's PTZ commands remain available, but the HTTP PTZ companion isn't launched in this Docker deployment. For now, use the separate instructions in [the full portable HA setup](../docs/PORTABLE_HOME_ASSISTANT_SETUP.md) and avoid exposing the companion on a public interface.

**HA OS users:** You can use this standalone bridge on a separate Linux host while keeping your existing HA OS instance. You do **not** need to install a Supervisor app.

## 6. Operational commands

```sh
docker compose ps
docker compose logs --tail=100
docker compose restart
docker compose stop
docker compose start
```

For an application update, pull this branch and rebuild explicitly after reading the changelog:

```sh
git pull --ff-only
docker compose up -d --build
```

**Stop and remove containers without deleting logins:**

```sh
docker compose down
```

Do **not** run `docker compose down --volumes` unless you deliberately want to delete saved Tuya sessions. Before a migration, copy the persistent session data into a securely stored backup; it contains authentication cookies.

## 7. Troubleshooting

| Symptom | Check |
| --- | --- |
| Browser UI unavailable | SSH tunnel terminal still running? `docker compose ps`? Is local port 8788 already used? |
| UI rejects credentials | `.env` username and 20+ char password, then `docker compose up -d` to recreate after changes |
| QR code never appears | Account region, cloud access, `docker compose logs --tail=100`, start a fresh login |
| Login succeeds but no cameras | `cameras refresh` and `cameras list`; check camera online in vendor app |
| RTSP unavailable remotely | Verify `RTSP_BIND_IP`, host firewall, Docker port binding and HA→bridge route |
| Video but no audio | Camera codecs and bridge RTSP SDP; PTT is separately installed |
| HA notification fails | Docker container can reach `HA_URL`; long-lived token permissions, correct HTTPS certificate |
| PTT doesn't work | HA custom integration/card installed? Browser HTTPS microphone permission? PCMU/8000? |

See [RTSP compatibility review](RTSP_COMPARISON.md), [the Home Assistant guide](../homeassistant/README.md) and [troubleshooting](../docs/TROUBLESHOOTING.md).

## Project status

- Not a replacement for an existing working host setup until fresh-install and real-camera testing succeeds.
- Existing Go PTT/PTZ code has not been replaced by the external fork.
- YaannnTech's RTSP remote-UDP and disconnect changes are under review; not yet integrated.
- For security, don't expose 8554 or 8788 publicly and don't send Tuya tokens or .env contents in bug reports.
