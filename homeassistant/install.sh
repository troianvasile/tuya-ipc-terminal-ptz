#!/usr/bin/env bash
# Install *files only* into a Home Assistant configuration directory.
# Does not restart Home Assistant or modify configuration.yaml or dashboards.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: bash homeassistant/install.sh /path/to/homeassistant/config" >&2
  exit 2
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$1"
if [ ! -d "$CONFIG" ]; then
  echo "Missing Home Assistant config directory: $CONFIG" >&2
  exit 1
fi

TARGET="$CONFIG/custom_components/little_elf_talk"
CARD="$CONFIG/www/little-elf-ptt-card.js"
PROCESSOR="$CONFIG/www/little-elf-talk-processor.js"
mkdir -p "$(dirname "$TARGET")" "$(dirname "$CARD")"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
if [ -d "$TARGET" ]; then
  mv "$TARGET" "${TARGET}.backup-$STAMP"
  echo "Backed up custom integration to ${TARGET}.backup-$STAMP"
fi
if [ -e "$CARD" ]; then
  cp -p "$CARD" "${CARD}.backup-$STAMP"
  echo "Backed up Lovelace card to ${CARD}.backup-$STAMP"
fi
if [ -e "$PROCESSOR" ]; then
  cp -p "$PROCESSOR" "${PROCESSOR}.backup-$STAMP"
  echo "Backed up AudioWorklet to ${PROCESSOR}.backup-$STAMP"
fi

mkdir -p "$TARGET"
install -m 0644 "$HERE/custom_components/little_elf_talk/__init__.py" "$TARGET/__init__.py"
install -m 0644 "$HERE/custom_components/little_elf_talk/rtsp_audio.py" "$TARGET/rtsp_audio.py"
install -m 0644 "$HERE/custom_components/little_elf_talk/manifest.json" "$TARGET/manifest.json"
install -m 0644 "$HERE/www/little-elf-ptt-card.js" "$CARD"
install -m 0644 "$HERE/www/little-elf-talk-processor.js" "$PROCESSOR"

echo
echo "Files installed. NEXT:"
echo "1. Configure little_elf_talk in configuration.yaml."
echo "2. Add /local/little-elf-ptt-card.js?v=0.1.0 as a JavaScript Lovelace resource."
echo "3. Restart Home Assistant manually, then test with one camera."
echo "No services were restarted by this script."
