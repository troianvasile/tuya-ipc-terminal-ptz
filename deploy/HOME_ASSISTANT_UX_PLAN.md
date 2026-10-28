# Native Home Assistant experience without Supervisor

The [YaannnTech HA app](https://github.com/YaannnTech/HA-Apps/tree/main/tuya_ipc_bridge)
is configured and operated inside Home Assistant using **Supervisor Ingress**.
That is a genuine UX benefit, but it cannot run unchanged on Home Assistant
Container: HA Container does not contain the Supervisor or App Store.

## Product target

After installation, the owner should be able to manage the integration from
**Home Assistant → Settings → Devices & services**, regardless of installation type.
The UI must include onboarding, Tuya account/region choice and QR login, discovered
camera list, RTSP status, PTT compatibility and PTZ capabilities, session expiry,
and re-login. The external Go bridge is a separately managed background service
(Docker or systemd); **not** a dependency on Home Assistant Supervisor.

## Implementation phases

1. **Standalone bridge foundation (current draft):** Docker Compose, private web
   UI, Tuya QR login, session status, RTSP restart, optional HA notifications.
   This is NOT a native HA configuration flow; host-side setup is still needed.
2. **HA custom integration (not yet implemented):** config-flow onboarding and
   authenticated backend proxy to the bridge management API, backed by a
   bridge-scoped service token. No user credentials or Tuya cookie values should
   enter Lovelace/front-end JavaScript.
3. **HA management view:** HA-native page/flow for account QR login, expiry alerts,
   camera discovery, camera capabilities and stream URLs. Use HA's authenticated
   websocket/HTTP backend and ensure request authorization; avoid a public QR UI.
4. **Optional HA OS App:** wrap the same standalone service for Supervisor
   convenience, but keep identical management API and HA integration for users
   running HA Container.

## Design rules

- Do not require `SUPERVISOR_TOKEN`, `bashio` or `http://supervisor`.
- Do not place Tuya secrets in the browser, dashboard YAML, log output or HA
  frontend storage.
- Standalone/HA endpoints must be isolated on local/private interfaces and
  authenticated; default RTSP is unauthenticated and stays private.
- Home Assistant may run on a different host; use an explicitly configured
  private address, never assume the same Docker network.
- The bundled browser PTT card and camera PTZ remain optional and retain their
  existing audio/network requirements.
- HA integration should not break the bridge when HA is stopped or upgraded.
- An embedded **Webpage dashboard** is at most a temporary shortcut; it is not
  equivalent to native HA integration or Supervisor Ingress, and HTTPS / browser
  iframe restrictions can block it.

## Fresh-install acceptance checklist

- Plain HA Container: clean Docker bridge setup, configure integration in HA,
  scan Tuya QR, see cameras and status, play RTSP, optional PTT/PTZ.
- HA OS: same HA integration and an optionally Supervisor-managed bridge app.
- Separate host: HA reaches bridge over VPN with restricted RTSP and management.
- Restart: sessions survive bridge/HA restarts; stale credentials alert and
  reauthentication works.
- Security: an ordinary HA user cannot manage camera credentials or initiate
  account login; admin-only configuration.
- Recovery: update/rollback without deleting the bridge's persistent volume.

**Status:** this is a design/acceptance document. Phase 1 is implemented in
the branch but awaits tests; phases 2–4 have not been implemented.
