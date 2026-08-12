#!/usr/bin/env bash
# Пост-установка Hermes-плагина: pip-зависимости + деплой desktop-виджета.
#
# Запускать ПОСЛЕ `hermes plugins install <repo>` (из установленной копии):
#     bash ~/.hermes/plugins/<name>/scripts/install.sh
# либо из dev-clone для быстрой итерации виджета.
#
# `hermes plugins install` сам НЕ запускает pip и НЕ копирует виджет — это делает данный скрипт.
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="$(basename "$PLUGIN_DIR")"

# HERMES_HOME: Windows -> %LOCALAPPDATA%\hermes, *nix -> ~/.hermes
if [ -z "${HERMES_HOME:-}" ]; then
  if [ -d "$HOME/AppData/Local/hermes" ]; then HERMES_HOME="$HOME/AppData/Local/hermes"
  else HERMES_HOME="$HOME/.hermes"; fi
fi

echo "Плагин:  $NAME"
echo "Репо:    $PLUGIN_DIR"
echo "Hermes:  $HERMES_HOME"
echo ""

# 1. Python-зависимости в venv Hermes
VENV_PY=""
for cand in \
  "$HERMES_HOME/hermes-agent/venv/Scripts/python.exe" \
  "$HERMES_HOME/hermes-agent/venv/bin/python" \
  "$HERMES_HOME/test_venv/Scripts/python.exe" \
  "$HERMES_HOME/test_venv/bin/python" ; do
  [ -x "$cand" ] && VENV_PY="$cand" && break
done
if [ -n "$VENV_PY" ] && [ -f "$PLUGIN_DIR/requirements.txt" ]; then
  echo "== pip install -r requirements.txt (в venv Hermes) =="
  "$VENV_PY" -m pip install -r "$PLUGIN_DIR/requirements.txt"
else
  echo "!! venv Hermes не найден или нет requirements.txt — pip пропущен."
  echo "   Поставьте вручную в venv Hermes: pip install -r requirements.txt"
fi
echo ""

# 2. Деплой desktop-виджета в сайдбар
if [ -f "$PLUGIN_DIR/scripts/deploy-desktop-plugin.sh" ]; then
  echo "== deploy desktop widget =="
  bash "$PLUGIN_DIR/scripts/deploy-desktop-plugin.sh"
else
  echo "!! scripts/deploy-desktop-plugin.sh не найден — виджет не развёрнут."
fi
echo ""

# 3. Включение + рестарт gateway — вручную
echo "== далее вручную =="
echo "  • включить плагин (если не ответили 'y' при install):"
echo "      добавить '$NAME' в plugins.enabled в $HERMES_HOME/config.yaml"
echo "      (или: hermes plugins enable $NAME)"
echo "  • перезапустить gateway:"
echo "      hermes gateway restart   (или закрыть и открыть Hermes Desktop)"
echo ""
echo "Готово. После рестарта — вкладка в сайдбаре (если не появилась: Ctrl/Cmd+K → Reload desktop plugins)."
