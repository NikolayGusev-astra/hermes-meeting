#!/bin/bash
# Deploy the Meeting Intelligence Hermes-Desktop sidebar plugin.
#
# `hermes plugins install` places the MCP/CLI plugin at ~/.hermes/plugins/meeting-intelligence,
# but the Hermes-Desktop UI sidebar widget lives in ~/.hermes/desktop-plugins/ and is NOT
# installed automatically. This script copies com.hermes.desktop/plugin.js there so the
# "Встречи" tab appears in the desktop app.
#
# Usage:  bash scripts/deploy-desktop-plugin.sh [<hermes-home>]
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_HOME="${1:-$HOME/.hermes}"
if [ -n "$HERMES_HOME" ] && [ -z "$(ls -d "$HERMES_HOME" 2>/dev/null)" ]; then
  # windows-style fallback (AppData\Local\hermes)
  HERMES_HOME="$HOME/AppData/Local/hermes"
fi

SRC="$REPO_DIR/com.hermes.desktop/plugin.js"
DEST_DIR="$HERMES_HOME/desktop-plugins/meeting-intelligence"
DEST="$DEST_DIR/plugin.js"

echo "Deploying Meeting Intelligence desktop plugin"
echo "  from: $SRC"
echo "  to:   $DEST"

if [ ! -f "$SRC" ]; then
  echo "ERROR: source $SRC not found"
  exit 1
fi

mkdir -p "$DEST_DIR"

# back up existing if different
if [ -f "$DEST" ] && ! diff -q "$SRC" "$DEST" >/dev/null 2>&1; then
  cp "$DEST" "$DEST_DIR/plugin.js.previous-$(date +%Y%m%d%H%M%S)"
fi

cp "$SRC" "$DEST"
echo "  ✓ deployed"

echo
echo "Restart the Hermes Desktop GUI (or reload the window) for the tab to appear."
echo "Next: verify the 'Встречи' tab renders in the sidebar."
