# Supervisor-free Tuya IPC Bridge (experimental branch)

This deployment runs the **existing Go RTSP / PTT-capable bridge** with a local
account-management web UI. It does **not** require Home Assistant OS or Supervisor.
It is designed for regular Linux and Docker Compose, with Home Assistant on the same
or a different machine.

## Quick start

```sh
git clone -b feature/supervisor-free-tuya-bridge https://github.com/troianvasile/tuya-ipc-terminal-ptz.git
cd tuya-ipc-terminal-ptz/deploy
cp .env.example .env
# Edit WEB_USERNAME and WEB_PASSWORD; optionally HA_URL and HA_TOKEN.
chmod 600 .env
docker compose up -d --build
docker compose logs -f --tail=80
```

Open the **local-only** account UI through an SSH tunnel:

```sh
ssh -L 8788:127.0.0.1:8788 USER@BRIDGE_HOST
```

Then visit http://127.0.0.1:8788/ and sign in using the credentials from .env.
Select a Tuya region and enter an account email, start QR login and scan the
resulting image with the built-in scanner in Tuya Smart/Smart Life. The browser
does not receive the raw QR token from the status endpoint. Authenticated sessions
and camera discovery are persisted in the Docker volume `tuya_data`.

Video stream: `rtsp://BRIDGE_HOST:8554/EXACT_DISCOVERED_PATH`.
Review `tuya-ipc-terminal cameras list` and `rtsp list-endpoints` inside the
container to identify the actual path:

```sh
docker compose exec tuya-bridge tuya-ipc-terminal cameras list
docker compose exec tuya-bridge tuya-ipc-terminal rtsp list-endpoints
```

For the existing HA browser microphone and PTZ control, follow
[../homeassistant/README.md](../homeassistant/README.md) and
[../docs/PORTABLE_HOME_ASSISTANT_SETUP.md](../docs/PORTABLE_HOME_ASSISTANT_SETUP.md).
The PTZ companion is *not* launched automatically by this Compose stack.
Do not replace any existing production systemd installation with this experiment.

## Security and operational notes

- RTSP has no authentication or encryption. The example publishes TCP 8554; firewall
  it to HA/trusted VPN sources **before startup**. Do not publicly expose it.
- UI binds to host 127.0.0.1 only; access it via SSH tunnel or an authenticated
  HTTPS reverse proxy, never raw over the public internet.
- The bridge contains Tuya session tokens; do not copy or commit the Docker volume.
- The UI requires HTTP Basic authentication and has no browser session cookies.
  Use a strong random password and TLS if reverse-proxied.
- QR login processes may contain a short-lived token in their captured stdout
  (not in routine logs); this is cleared after the job finishes.
- Optional HA notifications use `HA_URL` and a long-lived HA API token.
  Unset both to disable. Token must never be printed in logs.
- The process checks account sessions hourly and records invalid sessions in its UI.
  The RTSP process restarts if it exits; camera discovery refreshes at startup.
- This experimental package has not yet passed end-to-end tests on a fresh HA
  installation or on cameras outside the earlier EU/Little Elf environment.
