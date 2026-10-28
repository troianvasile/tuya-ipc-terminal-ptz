# Tuya IPC Bridge — integration inside Home Assistant (experimental)

This is a **native HA configuration flow**, not a Supervisor app. It connects
to the separately running Docker/Linux bridge through its authenticated
management API. It does not automatically start/install the Docker service.

## First-time setup

1. Set up the bridge from [../deploy/README.md](../deploy/README.md), but do not
   remove or alter any existing running systemd camera service.
2. Confirm the management endpoint is accessible **from the Home Assistant
   container/host**. By default it binds host 127.0.0.1:8788 and is only
   reachable on that host. For HA on a different host, provide an authenticated
   HTTPS reverse proxy over a trusted private network or VPN, rather than
   exposing an HTTP login on the public internet.
3. Clone this experimental branch on a machine able to write to HA's live
   configuration directory. If Home Assistant runs in Docker, find that host
   directory with:

   ```sh
   docker inspect homeassistant --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}'
   ```

4. Install only the HA integration files (it backs up an existing install):

   ```sh
   bash homeassistant/install-bridge.sh /path/to/real/ha/config
   ```

5. Validate Home Assistant configuration, restart HA when convenient, then
   navigate to **Settings → Devices & services → Add integration → Tuya IPC
   Bridge**. Enter the management URL and the username/password used in the
   Docker `.env`. Enter a URL reachable *from HA*, not from your browser.
6. Two status entities are created: **RTSP status** and **Accounts**. Status is
   refreshed approximately every minute. Authentication data stays in HA config
   entry storage and must be treated as a secret.

## Installation combinations

| HA installation | Bridge service |
| --- | --- |
| Home Assistant Container | Docker Compose on same or another Linux host |
| Home Assistant OS | Bridge on external Linux host; no Supervisor add-on required |
| HA Core | Bridge on same or separate host |

Home Assistant still needs network connectivity to the RTSP listener for video
and PTT. See [existing PTT install](README.md) for the separate microphone
card and PCMU/8000 restrictions.

## Current development stage

This initial native HA integration provides the config flow and status entities,
**not yet** full Tuya QR login or camera management within HA. QR login is
available in the private bridge UI (through SSH tunneling), and the existing
Go PTT/PTZ features remain separate. An authenticated HA-backed account UI
is the next implementation stage. We do not claim Supervisor-equivalent
onboarding until it has been built and physically tested.

## Security and troubleshooting

- Never put the bridge password in dashboard YAML or client-side JavaScript.
- Keep management endpoint reachable only via private VPN or authenticated
  HTTPS reverse proxy; never raw public HTTP.
- Don't assume the HA Container's `127.0.0.1` is the bridge host.
- Errors during HA setup: inspect `docker compose ps`, endpoint reachability
  and HA logs for `tuya_ipc_bridge`; don't paste credentials into issues.
- Uninstall: delete the integration in HA; stop HA, remove just the
  `custom_components/tuya_ipc_bridge` directory, and restart. This will
  not delete the Docker named volume holding Tuya sessions.
