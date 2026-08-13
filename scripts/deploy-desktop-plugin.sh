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

# Resolve HERMES_HOME (explicit arg > $HERMES_HOME env > OS convention).
# Critical on macOS: Hermes Desktop keeps its home under
# ~/Library/Application Support/hermes, NOT ~/.hermes — deploying the widget to
# the wrong home is why the "Встречи" tab is invisible on a clean Mac install.
detect_home() {
  if [ -n "$1" ]; then echo "$1"; return; fi
  if [ -n "$HERMES_HOME" ] && [ -d "$HERMES_HOME" ]; then echo "$HERMES_HOME"; return; fi
  case "$(uname -s)" in
    Darwin)            echo "$HOME/Library/Application Support/hermes" ;;
    MINGW*|MSYS*|CYGWIN*) echo "${LOCALAPPDATA:-$HOME/AppData/Local}/hermes" ;;
    *)                 echo "$HOME/.hermes" ;;
  esac
}
HERMES_HOME="$(detect_home "$1")"
if [ ! -d "$HERMES_HOME" ]; then
  echo "NOTE: каталог $HERMES_HOME ещё не существует — создаю."
  echo "      Если Hermes Desktop ни разу не запускался, запустите его хотя бы раз,"
  echo "      чтобы он создал home по этому пути, и повторите деплой."
  echo "      (macOS: ~/Library/Application Support/hermes · Windows: %LOCALAPPDATA%\\hermes)"
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
echo "Полностью перезапустите Hermes Desktop, чтобы вкладка появилась."
echo "  · macOS: ⌘Q (полный выход), не просто закрыть окно."
echo "  · Reload desktop plugins (⌘K) НЕ перечитывает новые плагины — нужен рестарт."
echo "Next: проверьте, что вкладка 'Встречи' отрисовалась в сайдбаре."
