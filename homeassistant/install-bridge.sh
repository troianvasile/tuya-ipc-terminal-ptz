#!/usr/bin/env bash
# Install native Tuya IPC Bridge integration files only (not the Go bridge/PTT).
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo "Usage: bash homeassistant/install-bridge.sh /path/to/ha/config" >&2
  exit 2
fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$1"
SOURCE="$HERE/custom_components/tuya_ipc_bridge"
TARGET="$CONFIG/custom_components/tuya_ipc_bridge"
if [ ! -d "$CONFIG" ] || [ ! -f "$CONFIG/configuration.yaml" ]; then
  echo "Not a Home Assistant config directory: $CONFIG" >&2
  exit 1
fi
for file in manifest.json __init__.py config_flow.py sensor.py const.py strings.json; do
  test -s "$SOURCE/$file" || { echo "Missing: $file" >&2; exit 1; }
done
mkdir -p "$CONFIG/custom_components"
if [ -e "$TARGET" ]; then
  STAMP="$(date -u +%Y%m%d-%H%M%S)"
  cp -a "$TARGET" "$TARGET.backup-$STAMP"
  echo "Backed up previous integration to $TARGET.backup-$STAMP"
fi
mkdir -p "$TARGET"
for file in manifest.json __init__.py config_flow.py sensor.py const.py strings.json; do
  install -m 0644 "$SOURCE/$file" "$TARGET/$file"
done
echo "Installed Tuya IPC Bridge configuration integration."
echo "Validate HA configuration; restart HA manually; then Settings -> Devices & services -> Add integration -> Tuya IPC Bridge."
echo "For browser microphone/PTT, also install the separate little_elf_talk integration."
