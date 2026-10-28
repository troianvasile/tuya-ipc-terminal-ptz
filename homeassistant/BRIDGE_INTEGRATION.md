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

## QR login and camera list inside Home Assistant (experimental)

The native integration now includes an admin-only WebSocket proxy, plus a
Lovelace management card. **This is not yet a custom panel inside Devices &
services.** Installation starts there, but the management UI lives on a dashboard.

1. After configuring Tuya IPC Bridge in **Settings → Devices & services**,
   locate the integration config entry's ID in Home Assistant's integration
   diagnostics/configuration metadata. This manual ID step will be removed as
   the installation UX improves.
2. Register `/local/tuya-bridge-manager.js` as a **JavaScript module** resource
   under Dashboards → Resources.
3. Add a manual card to a dashboard restricted to administrators:

   ```yaml
   type: custom:tuya-bridge-manager
   entry_id: REPLACE_WITH_HA_CONFIG_ENTRY_ID
   ```

4. Open the dashboard as an HA administrator. The card requests bridge status
   and discovered cameras through the HA backend. Choose region and email,
   select **Start QR login**, scan via Tuya Smart/Smart Life's built-in scanner.
   The QR image is relayed through HA; the bridge username/password remain
   server-side. The management API also remains accessible to the standalone
   SSH-tunnel UI.

**Important:** Hiding a dashboard from nonadmins is not an authorization
boundary. The backend enforces `connection.user.is_admin` on every management
command. A browser cannot call the bridge directly with HA-stored credentials.

The private bridge management address must be reachable from HA. By default
Docker maps it to host-local 127.0.0.1:8788, so HA on a different host
needs private networking or a restricted HTTPS reverse proxy.

## Current development stage

The branch now includes a basic HA management dashboard for QR login and a
read-only camera list. It is **not yet** an automatically discovered device
management experience or a native Settings panel. Camera setup, PTT and PTZ
still require their respective integration steps. Fresh-install validation,
UI usability improvements and regression tests remain pending.

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
