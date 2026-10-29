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
6. The integration automatically creates **RTSP status**, **Accounts**, and one
   native camera entity per discovered bridge camera. Status and discovery are
   refreshed approximately every minute. Authentication data stays in HA config
   entry storage and must be treated as a secret.
7. If HA and the browser reach the bridge through different addresses, fill
   **Bridge manager URL for this browser** with the browser-reachable private
   URL. HA uses it for the **Open bridge manager** link without exposing
   credentials.

## Installation combinations

| HA installation | Bridge service |
| --- | --- |
| Home Assistant Container | Docker Compose on same or another Linux host |
| Home Assistant OS | Bridge on external Linux host; no Supervisor add-on required |
| HA Core | Bridge on same or separate host |

Home Assistant still needs network connectivity to the RTSP listener for video,
incoming camera audio and PTT. PTT requires a camera that advertises a
PCMU/8000 RTSP backchannel.

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
   server-side. The card also offers bounded PTZ direction buttons for each
   discovered camera. It does not issue a PTZ action until an administrator
   presses a button.

## Push-to-talk card

Register `/local/little-elf-ptt-card.js` as a JavaScript module resource, then
add this manual card for any discovered camera:

```yaml
type: custom:little-elf-ptt-card
entry_id: REPLACE_WITH_HA_CONFIG_ENTRY_ID
camera_id: REPLACE_WITH_DISCOVERED_DEVICE_ID
```

This uses the dynamically discovered camera; no YAML `little_elf_talk` alias
or separate PTT backend is required. PTT is administrator-only and requires
browser microphone permission over HTTPS or localhost. It deliberately sends
only PCMU/8000 microphone packets over the bridge's private RTSP backchannel.

To update bridge credentials or the browser manager link, open the integration
menu and choose **Reconfigure**; deleting and re-adding it is unnecessary.

## Ready-to-go dashboard card

For the normal self-install path, register just
`/local/tuya-ipc-bridge-setup-card.js` as a JavaScript module resource and add:

```yaml
type: custom:tuya-ipc-bridge-setup-card
```

The card resolves the only configured bridge automatically. It renders every
discovered native camera with an HA camera widget, hold-to-talk control,
bounded PTZ directions and an **Open bridge manager** link. By default the
widget uses still frames, which is reliable for HEVC-only cameras; set
`live: true` when the camera/browser combination can play the generated HA
stream and incoming audio. If multiple bridge entries are configured, set
`entry_id` on the card explicitly. The linked manager page will still request
its own bridge credentials; none are passed in the URL.

**Important:** Hiding a dashboard from nonadmins is not an authorization
boundary. The backend enforces `connection.user.is_admin` on every management
command. A browser cannot call the bridge directly with HA-stored credentials.

The private bridge management address must be reachable from HA. By default
Docker maps it to host-local 127.0.0.1:8788, so HA on a different host
needs private networking or a restricted HTTPS reverse proxy.

## Current development stage

The branch now includes automatic native camera discovery with RTSP
video/incoming audio, optional browser PTT and admin-only PTZ controls through
the same private bridge. The management experience remains a dashboard card,
rather than a native Devices & services panel. Fresh-install and real-camera
PTT/PTZ validation are still required before broader compatibility claims.

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
